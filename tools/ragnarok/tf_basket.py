"""解析37: トレンドフォロー + ナンピン(押し目の買い増し)/ピラミッディング(順行の買い増し)。時間決済なし。
入口は解析36の Data/signals/apply_filter を使う。1つの束(basket)を持つ。
  mode 'nan': 逆行が step×ATR 進むごとに買い増し(最大 maxlegs 段、ロット ×mult)
  mode 'pyr': 順行が step×ATR 進むごとに買い増し(最大 maxlegs 段。買い増すたびに損切りを平均建値へ)
  損切り: 最初の建値から sl×ATR(束全体で一括)
  利確: 平均建値から tp×ATR で frac を先に決済し、残りは損切りを平均建値へ → 高値から trail×ATR で追いかけ
同じ足の中は、逆行を先に処理する(不利な側)。窓開けは始値で決済。
ナンピンで買い増しした足では、足の中の順番が分からないので利確は次の足から。
fine=(M1 の O,H,L,C,時刻) を渡すと、M15 のシグナルを M1 足で決済まで追う(足の中の順番の答え合わせ)。"""
import tf_model as t, numpy as np
def sim(d,s,mode='nan',step=1.0,maxlegs=3,mult=1.0,sl=5.0,tp=0.75,trail=4.0,frac=0.3,i0=0,i1=None,fine=None):
    m15t=d.o.index.values
    if fine is not None: O,H,L,C,mt=fine
    else: O,H,L,C=d.O,d.H,d.L,d.C
    i1=i1 or d.N; out=[]; i=max(i0,200); nb=len(O) if fine is not None else i1
    while i<i1-1:
        k=s[i]
        if k==0 or np.isnan(d.atr[i]): i+=1; continue
        if fine is not None:
            p0=int(np.searchsorted(mt,m15t[i+1]))
            if p0>=len(mt) or abs((mt[p0]-m15t[i+1])/np.timedelta64(1,'m'))>5: i+=1; continue
        else: p0=i+1
        e=O[p0]; sp=e*t.SPR; a=d.atr[i]; px=e+sp if k>0 else e
        legs=[(px,1.0)]; SL=px-k*sl*a; moved=False; booked=0.0; rem=1.0; best=px; ex=None; j=p0
        def avg():
            tl=sum(l for _,l in legs); return sum(p*l for p,l in legs)/tl
        while j<nb:
            hi=H[j]+(sp if k<0 else 0); lo=L[j]+(sp if k<0 else 0); op=O[j]+(sp if k<0 else 0); cl=C[j]+(sp if k<0 else 0)
            fav=hi if k>0 else lo; adv=lo if k>0 else hi
            if (op-SL)*k<=0: ex=op; break
            nleg0=len(legs)
            if mode=='nan' and not moved:
                while len(legs)<maxlegs:
                    lvl=legs[-1][0]-k*step*a
                    if (lvl-SL)*k<=0 or (adv-lvl)*k>0: break
                    legs.append((lvl,mult**len(legs)))
            if (adv-SL)*k<=0: ex=SL; break
            if mode=='pyr' and not moved:
                while len(legs)<maxlegs:
                    lvl=legs[-1][0]+k*step*a
                    if (fav-lvl)*k<0: break
                    legs.append((lvl,mult**len(legs)))
                    if (avg()-SL)*k>0: SL=avg()   # 買い増すたびに損切りを平均建値へ
                    if (cl-SL)*k<=0: ex=SL; break
                if ex is not None: break
            if not moved and len(legs)==nleg0:
                A=avg(); TP=A+k*tp*a
                if (fav-TP)*k>=0:
                    booked=frac*sum(l*(TP-p)*k for p,l in legs); rem=1-frac
                    SL=A+k*sp; moved=True; best=fav
                    if (cl-SL)*k<=0: ex=SL; break
                    j+=1; continue
            if moved:
                best=max(best,fav) if k>0 else min(best,fav); ns=best-k*trail*a
                if (ns-SL)*k>0:
                    SL=ns
                    if (cl-SL)*k<=0: ex=SL; break
            j+=1
        if ex is None:
            if fine is not None: break
            ex=C[i1-1]+(sp if k<0 else 0); j=i1-1
        pnl=booked+rem*sum(l*(ex-p)*k for p,l in legs)
        out.append((i,j,k,pnl,'basket',sum(l for _,l in legs),len(legs)))
        i=(j+1) if fine is None else max(i+1,int(np.searchsorted(m15t,mt[j],side='right')))
    return out
def stats(tr):
    if not tr: return dict(n=0,win=0,pf=0,exp=0,total=0,dd=0,maxlot=0,avglegs=0,worst=0)
    p=np.array([x[3] for x in tr]); w=p[p>0]; l=p[p<=0]
    cum=np.cumsum(p*t.YEN); dd=(cum-np.maximum.accumulate(np.r_[0,cum][1:])).min()
    return dict(n=len(p),win=round(100*len(w)/len(p),1),avgw=round(w.mean(),2) if len(w) else 0,avgl=round(l.mean(),2) if len(l) else 0,
        pf=round(w.sum()/-l.sum(),2) if l.sum()<0 else 99,exp=round(p.mean()*t.YEN,2),total=round(p.sum()*t.YEN),dd=round(dd),
        maxlot=round(max(x[5] for x in tr),2),avglegs=round(np.mean([x[6] for x in tr]),2),worst=round(p.min(),1))
