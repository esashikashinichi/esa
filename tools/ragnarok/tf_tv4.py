"""解析47: TradingView のエディターズピック級の公開インジケーター(everget HalfTrend、alexgrover Andean Oscillator、ChrisMoody CM Williams Vix Fix、jdehorty Nadaraya-Watson Envelope)を実装し、
M15・M5 で検証(解析45と同じ枠: フィルター4種 × 買い増しの形5種)。TV 本体は取得できないため、公開されているロジックを再現した近似実装。"""
import os, numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_tv as v, tf_tv3 as w
d=v.d; o=v.o; N=v.N; h,l,c=d.H,d.L,d.C; opn=d.O
def halftrend(amp,dev):
    atr2=t.atr(o,100).values/2; dv=dev*atr2; H=pd.Series(h); L=pd.Series(l)
    hp=H.rolling(amp).max().values; lp=L.rolling(amp).min().values; hma=H.rolling(amp).mean().values; lma=L.rolling(amp).mean().values
    trend=np.zeros(N,int); nxt=0; maxlow=l[0]; minhigh=h[0]
    for i in range(1,N):
        if np.isnan(hp[i]) or np.isnan(lma[i]): trend[i]=trend[i-1]; continue
        trend[i]=trend[i-1]
        if nxt==1:
            maxlow=max(lp[i],maxlow)
            if hma[i]<maxlow and c[i]<l[i-1]: trend[i]=1; nxt=0; minhigh=hp[i]
        else:
            minhigh=min(hp[i],minhigh)
            if lma[i]>minhigh and c[i]>h[i-1]: trend[i]=0; nxt=1; maxlow=lp[i]
    s=np.zeros(N,int); p=np.r_[0,trend[:-1]]; s[(trend==0)&(p==1)]=1; s[(trend==1)&(p==0)]=-1; s[:150]=0; return s
def andean(length,sig):
    a=2/(length+1); up1=np.zeros(N); up2=np.zeros(N); dn1=np.zeros(N); dn2=np.zeros(N); up1[0]=dn1[0]=c[0]; up2[0]=dn2[0]=c[0]**2
    for i in range(1,N):
        up1[i]=max(c[i],opn[i],up1[i-1]-(up1[i-1]-c[i])*a); up2[i]=max(c[i]**2,opn[i]**2,up2[i-1]-(up2[i-1]-c[i]**2)*a)
        dn1[i]=min(c[i],opn[i],dn1[i-1]+(c[i]-dn1[i-1])*a); dn2[i]=min(c[i]**2,opn[i]**2,dn2[i-1]+(c[i]**2-dn2[i-1])*a)
    bull=np.sqrt(np.maximum(dn2-dn1**2,0)); bear=np.sqrt(np.maximum(up2-up1**2,0)); sg=t.ema(pd.Series(np.maximum(bull,bear)),sig).values
    s=np.zeros(N,int); pb=np.r_[0,bull[:-1]]; pr=np.r_[0,bear[:-1]]; s[(bull>bear)&(pb<=pr)]=1; s[(bull<bear)&(pb>=pr)]=-1; s[:150]=0; return s
def vixfix(pd_=22,bbl=20,mult=2.0,lb=50,ph=0.85):
    C=pd.Series(c); Lw=pd.Series(l); Hw=pd.Series(h)
    def sig(x):
        mid=x.rolling(bbl).mean(); sd=mult*x.rolling(bbl).std(ddof=0); up=mid+sd; rh=x.rolling(lb).max()*ph; return ((x>=up)|(x>=rh)).values
    wvf=((C.rolling(pd_).max()-Lw)/C.rolling(pd_).max()*100); wvt=((Hw-C.rolling(pd_).min())/C.rolling(pd_).min()*100)
    gb=sig(wvf); gt=sig(wvt); s=np.zeros(N,int); pg=np.r_[False,gb[:-1]]; pt=np.r_[False,gt[:-1]]; s[gb&~pg]=1; s[gt&~pt]=-1; s[:150]=0; return s
def nadaraya(hh=8.0,mult=3.0,win=500):
    k=np.arange(0,5*int(hh)+1); wt=np.exp(-(k**2)/(2*hh*hh)); wt=wt/wt.sum(); nw=np.full(N,np.nan)
    for i in range(len(k),N): nw[i]=(c[i-len(k)+1:i+1][::-1]*wt).sum()
    mae=pd.Series(np.abs(c-nw)).rolling(win,min_periods=100).mean().values*mult; up=nw+mae; lo=nw-mae
    s=np.zeros(N,int); pc=np.r_[np.nan,c[:-1]]; pu=np.r_[np.nan,up[:-1]]; pl=np.r_[np.nan,lo[:-1]]
    s[(c<lo)&(pc>=pl)]=1; s[(c>up)&(pc<=pu)]=-1; s[:max(150,120)]=0; return s
SIG4={'HalfTrend(2,2)':lambda:halftrend(2,2),'HalfTrend(4,2)':lambda:halftrend(4,2),'Andean(50,9)':lambda:andean(50,9),'Andean(25,9)':lambda:andean(25,9),'VixFix(22)':lambda:vixfix(),'Nadaraya-Watson(8,3)':lambda:nadaraya(),'(基準)SQZ勢い0':lambda:v.squeeze('mom'),'(基準)ST(10,3)':lambda:v.supertrend(10,3.0),'(基準)DIクロス':lambda:v.dicross()}
CACHE={}
def sg(name,f):
    k=(name,f)
    if k not in CACHE:
        if name not in CACHE: CACHE[name]=SIG4[name]()
        CACHE[k]=t.apply_filter(d,CACHE[name],f) if f!='none' else CACHE[name]
    return CACHE[k]
def run(a):
    name,f,cn=a; cfg,sl0=v.CF[cn]; return dict(tf=v.TF,ind=name,flt=f,cfg=cn,**w.evalrun(sg(name,f),cfg,sl0))
if __name__=='__main__':
    for n in SIG4:
        for f in v.FIL: sg(n,f)
    A=[(n,f,cn) for n in SIG4 for f in v.FIL for cn in v.CF]
    with Pool() as pl: rows=pl.map(run,A,chunksize=4)
    pd.DataFrame(rows).to_csv(f'tf_tv4_{v.TF}.csv',index=False); print(v.TF,len(rows))
