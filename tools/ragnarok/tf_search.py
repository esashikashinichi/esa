"""解析36: 入口9種 × フィルター5種 × 出口67通り を、前期間(〜2025-12)と後期間(2026-01〜)で計算"""
import tf_model as t, numpy as np, pandas as pd, itertools
from multiprocessing import Pool
o=t.load_m15(); d=t.Data(o); CUT=int(np.searchsorted(o.index.values,np.datetime64('2026-01-01')))
ENTRIES=['don20','don55','x9_21','x20_50','pb_rsi','pb_ema','rsi2','macd','adx']
FILTERS=['none','h1','h4','h1h4','adx20']
EXITS=[('fix',dict(tp=tp,sl=sl)) for tp in (0.5,0.75,1,1.5,2,3) for sl in (1,1.5,2,3,4)]
EXITS+=[('fix',dict(tp=tp,sl=sl,be=be)) for tp in (1,1.5,2,3) for sl in (1.5,2,3) for be in (0.5,1.0)]
EXITS+=[('trail',dict(sl=sl,trail=tr)) for sl in (1,2,3) for tr in (1,2,3)]
EXITS+=[('opp',dict(sl=sl)) for sl in (2,3)]+[('sma5',dict(sl=sl)) for sl in (2,3)]
def f(a):
    e,fl=a; s=t.apply_filter(d,t.signals(d,e),fl); rows=[]
    for ex,kw in EXITS:
        A=t.stats(t.simulate(d,s,ex,i1=CUT,**kw)); B=t.stats(t.simulate(d,s,ex,i0=CUT,**kw))
        rows.append(dict(entry=e,filter=fl,exit=ex,**{k:kw.get(k) for k in ('tp','sl','be','trail')},
            **{'is_'+k:v for k,v in A.items()},**{'oos_'+k:v for k,v in B.items()}))
    return rows
if __name__=='__main__':
    with Pool(4) as p: R=p.map(f,list(itertools.product(ENTRIES,FILTERS)),chunksize=1)
    D=pd.DataFrame([r for rr in R for r in rr]); D.to_csv('tf_search.csv',index=False); print(len(D))
