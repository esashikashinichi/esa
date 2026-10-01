"""解析55: 上位5候補を1つの EA(別マジック・同じ口座)で同時に動かす。各候補を等倍(1単位=0.01ロット)で走らせ、
バーごとの損益を足して共通の複利倍率 m=floor((1万円+確定損益)/Kc)(最小1・最大30)で掛ける近似。Kc=合計の複利の強さ(各候補が m 倍、合計 5m 倍)。
M15 2.2年(i0=200)と M5 5か月(シグナルは M15・約定は M5)。通常とスプレッド2倍。"""
import numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl4 as sl, tf_rank as r, tf_rank_m5 as q
d=r.d; M=q.M; E0=r.E0; YEN=t.YEN
SETS={
 'A 速さ上位5(解析51)':['R または recross RSI2 ×1.5(利確0.3)','R + ピラミッディング ×1.5(利確0.3)','R または MACD押し(pb2+H4)(利確0.3)','R + ピラミッディング2段(利確0.3)','R + ピラミッディング2段(利確0.5)'],
 'B M5で頑健な5(型を分散)':['R または MACD押し(利確0.5)','DIクロス×MMT Fixed%zone×VixFix(H4+ADX)ナンピン2','DIクロス×MMT Fixed%flip×VixFix(H4+ADX)ナンピン2','Ichimoku TK+雲×MMT Fixed%flip ナンピン2','DIクロス+H4 ナンピン2段'],
 'C Rだけ(比較)':['R + ピラミッディング2段(利確0.5)']}
def stream(name,tf,spr):
    s,c,sl0=r.C[name]
    if tf=='M15': x=sl.engine(d.O,d.H,d.L,d.C,r.ev(name),r.cf(c),i0=200,spr=spr); i0=200
    else: x=sl.engine(M.O,M.H,M.L,M.C,q.ev5(name),r.cf(c),i0=1,spr=spr); i0=1
    n=len(x['eqc']); rz=np.zeros(n)
    for tr in x['trades']: rz[tr[1]]+=tr[0]
    return x['eqc'][i0:],x['eqa'][i0:],rz[i0:],i0
def comb(sn,tf,spr,Kc):
    S=[stream(n,tf,spr) for n in SETS[sn]]
    ec=sum(z[0] for z in S); ea=sum(z[1] for z in S); rz=sum(z[2] for z in S); i0=S[0][3]
    de=np.diff(ec,prepend=0.0); da=ea-np.r_[0.0,ec[:-1]]
    E=E0; Rr=0.0; peak=E0; mdd=0.0; first=None; mx=0
    idx=d.o.index[i0:] if tf=='M15' else M.m.index[1:]
    for j in range(len(ec)):
        m=max(1,min(30,int((E0+Rr)//Kc))); 
        adv=E+m*da[j]*YEN
        peak=max(peak,E); mdd=max(mdd,(peak-adv)/peak)
        E+=m*de[j]*YEN; Rr+=m*rz[j]*YEN; mx=max(mx,m)
        if first is None and E>=3*E0: first=(idx[j]-idx[0]).days
        if E<=0: break
    return E,mdd*100,first,len(S),mx
def one(a):
    sn,tf,spr,Kc=a; E,dd,f,ns,mx=comb(sn,tf,spr,Kc); return dict(set=sn,tf=tf,spr='2x' if spr else '1x',Kc=Kc,final=round(E),dd=round(dd,1),d3=f if f is not None else -1)
if __name__=='__main__':
    A=[(sn,tf,spr,Kc) for sn in SETS for tf in ('M15','M5') for spr in (None,t.SPR*2) for Kc in ((1000,) if sn.startswith('C') else (2500,5000,7500,10000))]
    with Pool() as pl: rows=pl.map(one,A)
    pd.DataFrame(rows).to_csv('tf_port.csv',index=False); print('done',len(rows))
