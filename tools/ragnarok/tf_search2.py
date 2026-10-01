"""解析36 第2段: 利確での勝率70%以上を狙う形(小さい利確・大きい損切り・部分決済)を細かく比べる"""
import tf_model as t, numpy as np, pandas as pd, itertools
from multiprocessing import Pool
o=t.load_m15(); d=t.Data(o); CUT=int(np.searchsorted(o.index.values,np.datetime64('2026-01-01')))
ENTRIES=['don40','don55','don80','don100','pb_ema','rsi2','x20_50','adx','macd']
FILTERS=['none','h4','h1h4','h4adx']
EXITS=[('fix',dict(tp=tp,sl=sl)) for tp in (0.5,0.75,1.0) for sl in (3,4,5,6)]
EXITS+=[('part',dict(tp=tp,sl=sl,trail=tr,frac=fr)) for tp in (0.5,0.75,1.0) for sl in (3,4,5) for tr in (2,3,4) for fr in (0.3,0.5,0.7)]
def f(a):
    e,fl=a; s=t.apply_filter(d,t.signals(d,e),fl); rows=[]
    for ex,kw in EXITS:
        A=t.stats(t.simulate(d,s,ex,i1=CUT,**kw)); B=t.stats(t.simulate(d,s,ex,i0=CUT,**kw))
        rows.append(dict(entry=e,filter=fl,exit=ex,**{k:kw.get(k) for k in ('tp','sl','trail','frac')},
            **{'is_'+k:v for k,v in A.items()},**{'oos_'+k:v for k,v in B.items()}))
    return rows
if __name__=='__main__':
    with Pool(4) as p: R=p.map(f,list(itertools.product(ENTRIES,FILTERS)),chunksize=1)
    D=pd.DataFrame([r for rr in R for r in rr]); D.to_csv('tf_search2.csv',index=False); print(len(D))
