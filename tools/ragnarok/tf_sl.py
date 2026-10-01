"""解析38: 損切り幅を変えて最適を探す。トレンドフォロー + ナンピン/ピラミッディング + 部分利確。
1つの方向に1つの束(買いと売りを同時に持てる)。
 損切り: 最初の建値から sl×ATR(束全体で一括。sl=inf なら損切り無し)。窓開けは始値で決済。slip×ATR だけ不利な値で決済。
 ナンピン: 逆行が nstep×ATR 進むごとに買い増し(最大 nl 回、ロット nmult^k)。ピラミッディング: 順行が pstep×ATR ごと(最大 pl 回、ロット pmult^k)。
 利確: 平均建値から tp×ATR で frac を先に決済(frac=1 なら全決済)。残りは損切りを平均建値+スプレッドへ動かし、高値から trail×ATR で追いかける。
 足の中は逆行を先に処理。買い増しした足では利確しない。M15 足だけを使う(M1 は使わない)。
 資金曲線は、部分利確で確定した分を含めて、足ごとに「確定済み + 含み損益」で作る。"""
import numpy as np, tf_model as t
def make_events(d,s):
    ev={}
    for i in range(200,d.N-1):
        k=int(s[i])
        if k!=0 and not np.isnan(d.atr[i]): ev.setdefault(i+1,[]).append((k,float(d.atr[i])))
    return ev
def engine(O,H,L,C,ev,cfg,i0=0,i1=None,both=True,spr=None):
    nl,nstep,nmult,pl,pstep,pmult,tp,frac,trail,sl,slip=cfg
    SPR=t.SPR if spr is None else spr
    n=len(O); i1=i1 or n
    bk=[None,None]; realized=0.0; entries=0; legs=0; trades=[]; maxtot=0.0
    eqc=np.zeros(n); eqa=np.zeros(n)
    for j in range(i0,i1):
        for k,a0 in ev.get(j,()):
            ix=0 if k>0 else 1
            if bk[ix] is not None: continue
            if not both and (bk[0] is not None or bk[1] is not None): continue
            sp=O[j]*SPR; px=O[j]+(sp if k>0 else 0.0)
            # k, a0, sp, tot, sumlp, lastnan, lastpyr, nnan, npyr, moved, rem, best, stop, t0, booked
            bk[ix]=[k,a0,sp,1.0,px,px,px,0,0,False,1.0,px,px-k*sl*a0,j,0.0]
            entries+=1; legs+=1
        flc=0.0; fla_=0.0
        for ix in (0,1):
            b=bk[ix]
            if b is None: continue
            k,a,sp=b[0],b[1],b[2]
            if k>0: hi=H[j]; lo=L[j]; op=O[j]; cl=C[j]; fav=hi; adv=lo
            else: hi=H[j]+sp; lo=L[j]+sp; op=O[j]+sp; cl=C[j]+sp; fav=lo; adv=hi
            ex=None; kind=None
            if (op-b[12])*k<=0:
                ex=op; kind='sl' if not b[9] else 'tr'
            elif not b[9]:
                added=False
                while b[7]<nl:
                    lvl=b[5]-k*nstep*a
                    if (adv-lvl)*k>0 or (lvl-b[12])*k<=0: break
                    lot=nmult**(b[7]+1); b[3]+=lot; b[4]+=lot*lvl; b[5]=lvl; b[7]+=1; added=True; legs+=1
                if (adv-b[12])*k<=0:
                    ex=b[12]-k*slip*a; kind='sl'
                else:
                    while b[8]<pl:
                        lvl=b[6]+k*pstep*a
                        if (fav-lvl)*k<0: break
                        lot=pmult**(b[8]+1); b[3]+=lot; b[4]+=lot*lvl; b[6]=lvl; b[8]+=1; added=True; legs+=1
                    if added and b[3]>maxtot: maxtot=b[3]
                    if not added:
                        A=b[4]/b[3]; TPp=A+k*tp*a
                        if (fav-TPp)*k>=0:
                            if frac>=1.0: ex=TPp; kind='tp'
                            else:
                                b[14]=frac*k*(TPp*b[3]-b[4]); b[10]=1.0-frac; b[9]=True; b[11]=fav
                                fl_=A+k*sp; ns=b[11]-k*trail*a
                                if (fl_-ns)*k>0: ns=fl_
                                b[12]=ns
                                if (cl-b[12])*k<=0: ex=b[12]; kind='tr'
            else:
                if (adv-b[12])*k<=0: ex=b[12]; kind='tr'
                else:
                    b[11]=max(b[11],fav) if k>0 else min(b[11],fav)
                    fl_=(b[4]/b[3])+k*sp; ns=b[11]-k*trail*a
                    if (fl_-ns)*k>0: ns=fl_
                    if (ns-b[12])*k>0: b[12]=ns
                    if (cl-b[12])*k<=0: ex=b[12]; kind='tr'
            if ex is not None:
                tp_=b[14]+k*b[10]*(ex*b[3]-b[4]); realized+=tp_; trades.append((tp_,j,b[13],kind,b[3])); bk[ix]=None
            else:
                flc+=b[14]+k*b[10]*(cl*b[3]-b[4]); fla_+=b[14]+k*b[10]*(adv*b[3]-b[4])
        eqc[j]=realized+flc; eqa[j]=realized+fla_
    return dict(eqc=eqc,eqa=eqa,entries=entries,legs=legs,trades=trades,open_end=sum(1 for b in bk if b is not None),maxtot=maxtot)
def summarize(res,i0,i1,segs,days,YEN=t.YEN):
    eqc,eqa=res['eqc'],res['eqa']; tr=[x for x in res['trades'] if i0<=x[1]<i1]
    p=np.array([x[0] for x in tr]) if tr else np.zeros(0)
    w=p[p>0]; l=p[p<=0]
    base=eqc[i0-1] if i0>0 else 0.0
    pk=np.maximum.accumulate(eqc[i0:i1]); dd=float((pk-eqa[i0:i1]).max())
    out=dict(n=len(p),win=100*len(w)/len(p) if len(p) else 0.0,pf=(w.sum()/-l.sum()) if l.sum()<0 else 99.0,
             pnl=float(eqc[i1-1]-base)*YEN,dd=dd*YEN,worst=float(p.min())*YEN if len(p) else 0.0,
             avgw=float(w.mean())*YEN if len(w) else 0.0,avgl=float(l.mean())*YEN if len(l) else 0.0,
             sl_pct=100*sum(1 for x in tr if x[3]=='sl')/len(tr) if tr else 0.0,
             entries=res['entries'],epd=res['entries']/days,open_end=res['open_end'],maxlot=res['maxtot']+1)
    sp=[]
    for a,b in segs:
        s0=eqc[a-1] if a>0 else 0.0; sp.append(float(eqc[b-1]-s0)*YEN)
    out['seg_pnl']=sp
    return out
