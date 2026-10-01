"""解析37: 入口3種 × 方式2種(押し目ナンピン/ピラミッディング) × 設定 を、前期間(〜2025-12)と後期間(2026-01〜)で計算"""
import tf_model as t, tf_basket as b, numpy as np, pandas as pd, itertools
from multiprocessing import Pool
o=t.load_m15(); d=t.Data(o); CUT=int(np.searchsorted(o.index.values,np.datetime64('2026-01-01')))
ENT=[('pb_ema','h1h4'),('rsi2','h4adx'),('don100','none')]
GRID=[]
for mode in ('nan','pyr'):
    for step in (0.5,0.75,1.0,1.5,2.0):
        for ml in (2,3,4,5):
            for mu in (1.0,1.5):
                for sl in (4,5,6,8):
                    for tp in (0.5,0.75,1.0):
                        for fr in (0.3,0.5):
                            GRID.append((mode,step,ml,mu,sl,tp,4.0,fr))
def f(a):
    (e,fl),cfgs=a; s=t.apply_filter(d,t.signals(d,e),fl); rows=[]
    for mode,step,ml,mu,sl,tp,trail,fr in cfgs:
        kw=dict(mode=mode,step=step,maxlegs=ml,mult=mu,sl=sl,tp=tp,trail=trail,frac=fr)
        A=b.stats(b.sim(d,s,i1=CUT,**kw)); B=b.stats(b.sim(d,s,i0=CUT,**kw))
        rows.append(dict(entry=e,filter=fl,**kw,**{'is_'+k:v for k,v in A.items()},**{'oos_'+k:v for k,v in B.items()}))
    return rows
if __name__=='__main__':
    jobs=[]
    for ef in ENT:
        for i in range(0,len(GRID),40): jobs.append((ef,GRID[i:i+40]))
    with Pool(4) as p: R=p.map(f,jobs,chunksize=1)
    D=pd.DataFrame([r for rr in R for r in rr]); D.to_csv('tf_basket2.csv',index=False); print('done',len(D))
