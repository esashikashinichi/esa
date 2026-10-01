"""解析50: MTF(1つ上の足)フィルターで、これまでのインジケーターを M1・M5・M15 で検証。上位足は M1→M5、M5→M15、M15→H1(確定した上位足のみ)。
MTF フィルター: mEMA = 上位足の終値 > EMA50(売りは逆)/ mST = 上位足の Supertrend(10,3)の向き / mDI = 上位足の +DI > -DI かつ ADX > 20 / mEMA+mDI = 両方。
TF=M1/M5/M15(環境変数)。"""
import sys, numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_tv as v, tf_tv3 as w, tf_tv4 as x4, tf_tv5 as x5
d=v.d; o=v.o; N=v.N; TF=v.TF
RULE={'M1':'5min','M5':'15min','M15':'1h'}[TF]
def htf_state():
    hb=o.resample(RULE,label='right',closed='right').agg({'O':'first','H':'max','L':'min','C':'last'}).dropna()
    ema=t.ema(hb.C,50); pos=np.sign(hb.C-ema)
    adx,pdi,ndi=t.adx(hb); di=pd.Series(np.where(adx>20,np.sign(pdi-ndi),0),index=hb.index)
    h_,l_,c_=hb.H.values,hb.L.values,hb.C.values; n=len(hb); atr=t.atr(hb,10).values; hl2=(h_+l_)/2; ub=hl2+3*atr; lb=hl2-3*atr; fub=ub.copy(); flb=lb.copy(); dr=np.ones(n,int)
    for i in range(1,n):
        if np.isnan(atr[i]): dr[i]=dr[i-1]; continue
        fub[i]=ub[i] if (ub[i]<fub[i-1] or c_[i-1]>fub[i-1] or np.isnan(fub[i-1])) else fub[i-1]
        flb[i]=lb[i] if (lb[i]>flb[i-1] or c_[i-1]<flb[i-1] or np.isnan(flb[i-1])) else flb[i-1]
        dr[i]=1 if (dr[i-1]==-1 and c_[i]>fub[i]) else (-1 if (dr[i-1]==1 and c_[i]<flb[i]) else dr[i-1])
    st=pd.Series(dr,index=hb.index)
    f=lambda s:s.reindex(o.index,method='ffill').fillna(0).values.astype(int)   # 確定した上位足(右端ラベル)だけを使う
    return dict(mEMA=f(pos),mST=f(st),mDI=f(di))
HS=htf_state()
def mtf(s,f):
    s=s.copy()
    if f=='none': return s
    keys={'mEMA':['mEMA'],'mST':['mST'],'mDI':['mDI'],'mEMA+mDI':['mEMA','mDI']}[f]
    for k in keys: s[(s==1)&(HS[k]!=1)]=0; s[(s==-1)&(HS[k]!=-1)]=0
    return s
def get(n):
    if n=='RSI2押し': return t.signals(d,'rsi2')
    if n.startswith('MMT '): return x5.SIGS[n[4:]]
    if n in v.SIG: return w.raw(n)
    if n not in x4.CACHE: x4.CACHE[n]=x4.SIG4[n]()
    return x4.CACHE[n]
INDS=list(v.SIG.keys())+['HalfTrend(2,2)','HalfTrend(4,2)','Andean(50,9)','VixFix(22)','Nadaraya-Watson(8,3)']+['MMT '+m for m in ('ATR(14,3) flip','Chandelier(22,14,2) zone','Donchian(40) flip','Fixed%(1.0) flip','Fixed%(1.0) zone','StdDev(20,2) flip')]+['RSI2押し']
FL=['none','mEMA','mST','mDI','mEMA+mDI']
CFC=w.CFC
def run(a):
    n,f,cn=a; cfg,sl0=CFC[cn]; s=mtf(get(n),f); return dict(tf=TF,htf=RULE,ind=n,flt=f,cfg=cn,**w.evalrun(s,cfg,sl0))
if __name__=='__main__':
    for n in INDS: get(n)
    A=[(n,f,cn) for n in INDS for f in FL for cn in CFC]
    with Pool() as pl: rows=pl.map(run,A,chunksize=8)
    pd.DataFrame(rows).to_csv(f'tf_mtf_{TF}.csv',index=False); print(TF,RULE,len(rows),'本',N)
