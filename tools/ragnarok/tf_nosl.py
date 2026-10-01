"""解析38: 損切り無しのトレンドフォロー(ナンピン・ピラミッディング有り)。資金曲線(含み損込み)で評価する。
1つの方向に1つの束(買いの束・売りの束を同時に持てる)。
 ナンピン: 逆行が nstep×ATR 進むごとに買い増し(最大 nl 回、ロット nmult^k)
 ピラミッディング: 順行が pstep×ATR 進むごとに買い増し(最大 pl 回、ロット pmult^k)
 利確: 平均建値から tp×ATR で frac を先に決済(frac=1.0 なら全決済)。残りは「平均建値+スプレッド」を下限に、高値から trail×ATR で追いかけて決済。
 損切りは無い(負けた束は利確するまで持つ)。足の中は逆行を先に処理。買い増しした足では利確しない(次の足から)。
 期末に残った束は最後の終値で評価して損益に入れる。
"""
import numpy as np, tf_model as t
def make_events(d,s):
    ev={}
    for i in range(200,d.N-1):
        k=int(s[i])
        if k!=0 and not np.isnan(d.atr[i]): ev.setdefault(i+1,[]).append((k,float(d.atr[i])))
    return ev
def engine(O,H,L,C,ev,cfg,i0=0,i1=None,both=True,spr=None):
    nl,nstep,nmult,pl,pstep,pmult,tp,frac,trail=cfg
    SPR=t.SPR if spr is None else spr
    n=len(O); i1=i1 or n
    bk=[None,None]; realized=0.0; entries=0; legs=0; closed=0; hold=[]; maxtot=0.0
    eqc=np.zeros(n); eqa=np.zeros(n); fla=np.zeros(n)
    for j in range(i0,i1):
        for k,a0 in ev.get(j,()):
            ix=0 if k>0 else 1
            if bk[ix] is not None: continue
            if not both and (bk[0] is not None or bk[1] is not None): continue
            sp=O[j]*SPR; px=O[j]+(sp if k>0 else 0.0)
            bk[ix]=[k,a0,sp,1.0,px,px,px,0,0,False,1.0,px,0.0,j]  # k,a0,sp,tot,sumlp,lastnan,lastpyr,nnan,npyr,moved,rem,best,stop,t0
            entries+=1; legs+=1
        flc=0.0; fla_=0.0
        for ix in (0,1):
            b=bk[ix]
            if b is None: continue
            k,a,sp=b[0],b[1],b[2]
            if k>0: hi=H[j]; lo=L[j]; op=O[j]; cl=C[j]; fav=hi; adv=lo
            else: hi=H[j]+sp; lo=L[j]+sp; op=O[j]+sp; cl=C[j]+sp; fav=lo; adv=hi
            ex=None
            if b[9]:   # 追いかけ中
                if (op-b[12])*k<=0: ex=op
                elif (adv-b[12])*k<=0: ex=b[12]
                else:
                    b[11]=max(b[11],fav) if k>0 else min(b[11],fav)
                    fl_=(b[4]/b[3])+k*sp; ns=b[11]-k*trail*a
                    if (fl_-ns)*k>0: ns=fl_
                    if (ns-b[12])*k>0: b[12]=ns
                    if (cl-b[12])*k<=0: ex=b[12]
            else:
                added=False
                while b[7]<nl:
                    lvl=b[5]-k*nstep*a
                    if (adv-lvl)*k>0: break
                    lot=nmult**(b[7]+1); b[3]+=lot; b[4]+=lot*lvl; b[5]=lvl; b[7]+=1; added=True; legs+=1
                while b[8]<pl:
                    lvl=b[6]+k*pstep*a
                    if (fav-lvl)*k<0: break
                    lot=pmult**(b[8]+1); b[3]+=lot; b[4]+=lot*lvl; b[6]=lvl; b[8]+=1; added=True; legs+=1
                if added and b[3]>maxtot: maxtot=b[3]
                if not added:
                    A=b[4]/b[3]; TPp=A+k*tp*a
                    if (fav-TPp)*k>=0:
                        if frac>=1.0: ex=TPp; b[10]=1.0
                        else:
                            realized+=frac*k*(TPp*b[3]-b[4]); b[10]=1.0-frac; b[9]=True; b[11]=fav
                            fl_=A+k*sp; ns=max(fav-k*0,0)  # placeholder
                            ns=b[11]-k*trail*a
                            if (fl_-ns)*k>0: ns=fl_
                            b[12]=ns
                            if (cl-b[12])*k<=0: ex=b[12]
            if ex is not None:
                realized+=k*b[10]*(ex*b[3]-b[4]); closed+=1; hold.append(j-b[13]); bk[ix]=None
            else:
                flc+=k*b[10]*(cl*b[3]-b[4]); fla_+=k*b[10]*(adv*b[3]-b[4])
        eqc[j]=realized+flc; eqa[j]=realized+fla_; fla[j]=fla_
    return dict(eqc=eqc,eqa=eqa,fla=fla,entries=entries,legs=legs,closed=closed,hold=hold,open_end=sum(1 for b in bk if b is not None),maxtot=maxtot)

def longest_under(eqc,i0,i1,bpd):
    x=eqc[i0:i1]; pk=np.maximum.accumulate(x); u=x<pk-1e-9
    best=cur=0
    for v in u:
        if v: cur+=1; best=max(best,cur)
        else: cur=0
    return best/bpd
def summarize(res,i0,i1,segs,bpd,days):
    eqc,eqa,fla=res['eqc'],res['eqa'],res['fla']
    base=eqc[i0-1] if i0>0 else 0.0
    pk=np.maximum.accumulate(eqc[i0:i1]); dd=float((pk-eqa[i0:i1]).max())
    out=dict(pnl=float(eqc[i1-1]-base),maxfl=float(fla[i0:i1].min()),dd=dd,entries=res['entries'],legs=res['legs'],closed=res['closed'],
             open_end=res['open_end'],epd=res['entries']/days,lpd=res['legs']/days,maxlot=res['maxtot']+1,
             hold_med=float(np.median(res['hold'])/bpd*24) if res['hold'] else 0.0,hold_p90=float(np.percentile(res['hold'],90)/bpd*24) if res['hold'] else 0.0,
             under=longest_under(eqc,i0,i1,bpd))
    sp=[]; sf=[]
    for a,b in segs:
        s0=eqc[a-1] if a>0 else 0.0
        sp.append(float(eqc[b-1]-s0)); sf.append(float(fla[a:b].min()))
    out['seg_pnl']=sp; out['seg_maxfl']=sf
    return out
