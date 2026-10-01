"""解析45: TradingView の代表的なインジケーターのシグナルを実装し、GOLD の M15(2.2年)と M5(約5か月)で、
買い増しなし/ピラミッディング/ナンピンの形ごとに勝率・PF を測る。出口は R と同じ形(部分利確 + 追いかけ、損切り)。
TF=M15 または M5(環境変数 TF)。M5 は M5 足そのものでシグナル・ATR を作る(M15 のシグナルを使わない)。"""
import os, itertools, numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl4 as sl
TF=os.environ.get('TF','M15')
o=t.load_m15({'M15':'../data/GOLDmicro15.csv','M5':'../data/GOLDmicro5.csv','M1':'../data/M1_long.csv'}[TF]); d=t.Data(o); N=d.N
DAYS=len(set(o.index.date)); idx=o.index
h,l,c=d.H,d.L,d.C
def sgn_flip(dirn):
    s=np.zeros(N,int); p=np.r_[0,dirn[:-1]]; s[(dirn==1)&(p<=0)]=1; s[(dirn==-1)&(p>=0)]=-1; return s
def supertrend(n,f):
    atr=t.atr(o,n).values; hl2=(h+l)/2; ub=hl2+f*atr; lb=hl2-f*atr; fub=ub.copy(); flb=lb.copy(); dr=np.zeros(N,int); dr[0]=1
    for i in range(1,N):
        if np.isnan(atr[i]): dr[i]=dr[i-1]; continue
        fub[i]=ub[i] if (ub[i]<fub[i-1] or c[i-1]>fub[i-1] or np.isnan(fub[i-1])) else fub[i-1]
        flb[i]=lb[i] if (lb[i]>flb[i-1] or c[i-1]<flb[i-1] or np.isnan(flb[i-1])) else flb[i-1]
        dr[i]=1 if (dr[i-1]==-1 and c[i]>fub[i]) else (-1 if (dr[i-1]==1 and c[i]<flb[i]) else dr[i-1])
    s=sgn_flip(dr); s[:60]=0; return s
def utbot(a,n):
    atr=t.atr(o,n).values; stop=np.zeros(N); s=np.zeros(N,int)
    for i in range(1,N):
        nl=a*atr[i] if not np.isnan(atr[i]) else 0; p=stop[i-1]
        if c[i]>p and c[i-1]>p: stop[i]=max(p,c[i]-nl)
        elif c[i]<p and c[i-1]<p: stop[i]=min(p,c[i]+nl)
        elif c[i]>p: stop[i]=c[i]-nl
        else: stop[i]=c[i]+nl
        if c[i]>stop[i] and c[i-1]<=stop[i-1]: s[i]=1
        elif c[i]<stop[i] and c[i-1]>=stop[i-1]: s[i]=-1
    s[:60]=0; return s
def rangefilter(per,mult):
    cs=pd.Series(c); rng=t.ema(cs.diff().abs(),per); r=(t.ema(rng,per*2-1)*mult).values; f=np.zeros(N); f[0]=c[0]; dr=np.zeros(N,int)
    for i in range(1,N):
        ri=r[i] if not np.isnan(r[i]) else 0
        f[i]=max(f[i-1],c[i]-ri) if c[i]>f[i-1] else min(f[i-1],c[i]+ri)
        dr[i]=1 if f[i]>f[i-1] else (-1 if f[i]<f[i-1] else dr[i-1])
    s=sgn_flip(dr); s[:max(60,per*3)]=0; return s
def linreg_last(y,n):
    x=np.arange(n); xm=x.mean(); den=((x-xm)**2).sum()
    def f(w): return w.mean()+((x-xm)*(w-w.mean())).sum()/den*(n-1-xm)
    return y.rolling(n).apply(f,raw=True)
def squeeze(kind):
    cs=pd.Series(c); sma=cs.rolling(20).mean(); sd=cs.rolling(20).std(ddof=0); tr=pd.concat([pd.Series(h-l),(pd.Series(h)-cs.shift()).abs(),(pd.Series(l)-cs.shift()).abs()],axis=1).max(axis=1)
    kr=tr.rolling(20).mean(); ub=sma+2*sd; lb=sma-2*sd; uk=sma+1.5*kr; lk=sma-1.5*kr; on=((lb>lk)&(ub<uk)).values
    hh=pd.Series(h).rolling(20).max(); ll=pd.Series(l).rolling(20).min(); val=linreg_last(cs-((hh+ll)/2+sma)/2,20).values
    s=np.zeros(N,int); p_on=np.r_[False,on[:-1]]
    if kind=='fire':
        f=p_on&~on; s[f&(val>0)]=1; s[f&(val<0)]=-1
    else:
        pv=np.r_[np.nan,val[:-1]]; s[(~on)&(val>0)&(pv<=0)]=1; s[(~on)&(val<0)&(pv>=0)]=-1
    s[:80]=0; return s
def wavetrend(kind):
    ap=pd.Series((h+l+c)/3); esa=t.ema(ap,10); dd=t.ema((ap-esa).abs(),10); ci=(ap-esa)/(0.015*dd); w1=t.ema(ci,21); w2=w1.rolling(4).mean(); w1=w1.values; w2=w2.values
    pw1=np.r_[np.nan,w1[:-1]]; pw2=np.r_[np.nan,w2[:-1]]; up=(w1>w2)&(pw1<=pw2); dn=(w1<w2)&(pw1>=pw2); s=np.zeros(N,int)
    if kind=='os': s[up&(w1<-53)]=1; s[dn&(w1>53)]=-1
    else: s[up&(w1<0)]=1; s[dn&(w1>0)]=-1
    s[:80]=0; return s
def ichimoku(kind):
    H=pd.Series(h); L=pd.Series(l); tk=(H.rolling(9).max()+L.rolling(9).min())/2; kj=(H.rolling(26).max()+L.rolling(26).min())/2
    sa=((tk+kj)/2).shift(26); sb=((H.rolling(52).max()+L.rolling(52).min())/2).shift(26); top=np.maximum(sa,sb).values; bot=np.minimum(sa,sb).values; tk=tk.values; kj=kj.values
    P=lambda a:np.r_[np.nan,a[:-1]]; s=np.zeros(N,int)
    if kind=='tk': s[(tk>kj)&(P(tk)<=P(kj))&(c>top)]=1; s[(tk<kj)&(P(tk)>=P(kj))&(c<bot)]=-1
    else: s[(c>top)&(P(c)<=P(top))]=1; s[(c<bot)&(P(c)>=P(bot))]=-1
    s[:120]=0; return s
def psar(af0=0.02,afs=0.02,afm=0.2):
    up=True; sar=l[0]; ep=h[0]; af=af0; dr=np.ones(N,int)
    for i in range(2,N):
        sar=sar+af*(ep-sar)
        if up:
            sar=min(sar,l[i-1],l[i-2])
            if l[i]<sar: up=False; sar=ep; ep=l[i]; af=af0
            elif h[i]>ep: ep=h[i]; af=min(af+afs,afm)
        else:
            sar=max(sar,h[i-1],h[i-2])
            if h[i]>sar: up=True; sar=ep; ep=h[i]; af=af0
            elif l[i]<ep: ep=l[i]; af=min(af+afs,afm)
        dr[i]=1 if up else -1
    s=sgn_flip(dr); s[:60]=0; return s
def wma(x,n):
    w=np.arange(1,n+1); return x.rolling(n).apply(lambda a:(a*w).sum()/w.sum(),raw=True)
def hma(n):
    cs=pd.Series(c); hm=wma(2*wma(cs,n//2)-wma(cs,n),int(np.sqrt(n))).values; dr=np.sign(np.r_[0,np.diff(hm)]); dr=np.nan_to_num(dr).astype(int); s=sgn_flip(dr); s[:80]=0; return s
def dicross():
    P=lambda a:np.r_[np.nan,a[:-1]]; s=np.zeros(N,int); s[(d.pdi>d.ndi)&(P(d.pdi)<=P(d.ndi))&(d.adx>20)]=1; s[(d.pdi<d.ndi)&(P(d.pdi)>=P(d.ndi))&(d.adx>20)]=-1; s[:200]=0; return s
SIG={'ST(10,3)':lambda:supertrend(10,3.0),'ST(10,2)':lambda:supertrend(10,2.0),'ST(14,2)':lambda:supertrend(14,2.0),'UT(1,10)':lambda:utbot(1.0,10),'UT(2,10)':lambda:utbot(2.0,10),
 'RF(100,3)':lambda:rangefilter(100,3.0),'RF(50,2)':lambda:rangefilter(50,2.0),'SQZ発火':lambda:squeeze('fire'),'SQZ勢い0':lambda:squeeze('mom'),'WT逆張り±53':lambda:wavetrend('os'),'WT0クロス':lambda:wavetrend('zero'),
 'Ichi TK+雲':lambda:ichimoku('tk'),'Ichi 雲抜け':lambda:ichimoku('cb'),'PSAR':lambda:psar(),'HMA21':lambda:hma(21),'DIクロス':lambda:dicross(),'(参考)EMA9/21':lambda:t.signals(d,'x9_21'),'(参考)Donchian55':lambda:t.signals(d,'don55'),'(参考)MACD':lambda:t.signals(d,'macd')}
FIL=['none','h4','h1h4','h4adx']
# (nl,nstep,nmult,pl,pstep,pmult,tp,frac,trail,sl,slip,be,pa), 損切り(make_events の sl0)
CF={'買増し無し':((0,1,1,0,1.0,1.0,0.5,0.3,4,5.0,0.1,0,0),5.0),'ピラ2':((0,1,1,2,1.0,1.0,0.5,0.3,4,5.0,0.1,0,0),5.0),'ピラ2 利確0.3':((0,1,1,2,1.0,1.0,0.3,0.3,4,5.0,0.1,0,0),5.0),
    'ナンピン2':((2,1,1.5,0,1.0,1.0,0.5,0.3,4,8.0,0.1,0,0),8.0),'ナンピン2+ピラ2 利確0.3':((2,1,1.5,2,1.0,1.0,0.3,0.3,4,8.0,0.1,0,0),8.0)}
P5=['2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01','2026-09-22'] if TF=='M15' else None
if TF=='M15': IDX=[int(np.searchsorted(idx.values,np.datetime64(x))) for x in P5]; IDX[0]=200
else: q=np.linspace(200,N,5).astype(int); IDX=list(q)
SEG=list(zip(IDX[:-1],IDX[1:])); HALF=(200+N)//2
CACHE={}
def sig(name,f):
    k=(name,f)
    if k not in CACHE:
        if name not in CACHE: CACHE[name]=SIG[name]()
        CACHE[k]=t.apply_filter(d,CACHE[name],f) if f!='none' else CACHE[name]
    return CACHE[k]
def run(a):
    name,f,cn=a; cfg,sl0=CF[cn]; s=sig(name,f); ev=sl.make_events(d,s,None,sl0); r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200)
    x=sl.summarize(r,200,N,SEG,DAYS); b1=sl.summarize(r,200,HALF,[(200,HALF)],len(set(idx.date[200:HALF]))); b2=sl.summarize(r,HALF,N,[(HALF,N)],len(set(idx.date[HALF:])))
    return dict(tf=TF,ind=name,flt=f,cfg=cn,N=x['n'],win=x['win'],pf=x['pf'],pnl=x['pnl'],dd=x['dd'],worst=x['worst'],epd=x['epd'],maxlot=x['maxlot'],pf_is=b1['pf'],pf_oos=b2['pf'],pos=sum(1 for v in x['seg_pnl'] if v>0),nseg=len(x['seg_pnl']))
if __name__=='__main__':
    A=[(n,f,cn) for n in SIG for f in FIL for cn in CF]
    for n in SIG:
        for f in FIL: sig(n,f)
    with Pool() as pl: rows=pl.map(run,A,chunksize=4)
    x=pd.DataFrame(rows); x.to_csv(f'tf_tv_{TF}.csv',index=False); print(TF,'全',len(x),'通り / 1日',N,'本')
