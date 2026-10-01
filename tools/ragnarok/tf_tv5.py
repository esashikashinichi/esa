"""解析48: RedK Multi-Modal Trailing Stop (RedK MMTStop v1.0) の再現。Pine のロジックどおり(ratchet・trend 判定)。
方式: ATR/Supertrend(anchor=hl2 ± ATR×倍率)、Chandelier(高値/安値 ± ATR×倍率)、Donchian(直近安値/高値)、StdDev(anchor ± stdev×倍率)、Fixed %。
入口: flip(trend の反転)/ zone(安全ゾーンの警戒帯 = ストップまで safeZone/2 ATR 未満 から離れた時の押し目)。TF=M15/M5。"""
import numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_tv as v, tf_tv3 as w
d=v.d; o=v.o; N=v.N; h,l,c=d.H,d.L,d.C
def mmt(mode,p1,p2=None,p3=None):
    hl2=(h+l)/2
    if mode=='atr': a=t.atr(o,p1).values*p2; lo=hl2-a; hi=hl2+a
    elif mode=='chand':
        ch=pd.Series(h).rolling(p1).max().values; cl=pd.Series(l).rolling(p1).min().values; at=t.atr(o,p2).values*p3; lo=ch-at; hi=cl+at
    elif mode=='donc': lo=pd.Series(l).rolling(p1).min().values; hi=pd.Series(h).rolling(p1).max().values
    elif mode=='sd': sd=pd.Series(hl2).rolling(p1).std(ddof=0).values*p2; lo=hl2-sd; hi=hl2+sd
    else: dd=hl2*p1/100; lo=hl2-dd; hi=hl2+dd
    up=np.zeros(N); dn=np.zeros(N); tr=np.ones(N,int); up[0]=lo[0] if not np.isnan(lo[0]) else 0; dn[0]=hi[0] if not np.isnan(hi[0]) else 0
    for i in range(1,N):
        if np.isnan(lo[i]) or np.isnan(hi[i]): up[i]=up[i-1]; dn[i]=dn[i-1]; tr[i]=tr[i-1]; continue
        up[i]=max(lo[i],up[i-1]) if c[i-1]>up[i-1] else lo[i]
        dn[i]=min(hi[i],dn[i-1]) if c[i-1]<dn[i-1] else hi[i]
        tr[i]=1 if c[i]>dn[i-1] else (-1 if c[i]<up[i-1] else tr[i-1])
    stop=np.where(tr==1,up,dn); return tr,stop
def flips(tr,warm):
    s=np.zeros(N,int); p=np.r_[0,tr[:-1]]; s[(tr==1)&(p==-1)]=1; s[(tr==-1)&(p==1)]=-1; s[:warm]=0; return s
def zone(tr,stop,safe=2.0):
    gap=np.abs(c-stop)/t.atr(o,14).values; pg=np.r_[np.nan,gap[:-1]]; wz=safe/2; s=np.zeros(N,int)
    s[(tr==1)&(pg<wz)&(gap>=wz)]=1; s[(tr==-1)&(pg<wz)&(gap>=wz)]=-1; s[:200]=0; return s
CASES={'ATR(10,3)':('atr',10,3.0),'ATR(10,2)':('atr',10,2.0),'ATR(14,3)':('atr',14,3.0),'ATR(10,5)':('atr',10,5.0),'Chandelier(22,14,3)':('chand',22,14,3.0),'Chandelier(22,14,2)':('chand',22,14,2.0),
 'Donchian(20)':('donc',20),'Donchian(10)':('donc',10),'Donchian(40)':('donc',40),'StdDev(20,2)':('sd',20,2.0),'StdDev(20,3)':('sd',20,3.0),'Fixed%(0.5)':('pct',0.5),'Fixed%(1.0)':('pct',1.0)}
SIGS={}
for k,a in CASES.items():
    tr,stop=mmt(*a); SIGS[k+' flip']=flips(tr,200); SIGS[k+' zone']=zone(tr,stop)
CACHE={}
def sg(name,f):
    k=(name,f)
    if k not in CACHE: CACHE[k]=t.apply_filter(d,SIGS[name],f) if f!='none' else SIGS[name]
    return CACHE[k]
def run(a):
    name,f,cn=a; cfg,sl0=v.CF[cn]; return dict(tf=v.TF,ind=name,flt=f,cfg=cn,**w.evalrun(sg(name,f),cfg,sl0))
if __name__=='__main__':
    A=[(n,f,cn) for n in SIGS for f in v.FIL for cn in v.CF]
    with Pool() as pl: rows=pl.map(run,A,chunksize=8)
    pd.DataFrame(rows).to_csv(f'tf_tv5_{v.TF}.csv',index=False); print(v.TF,len(rows))
