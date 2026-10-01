"""解析53: R のピラミッディングを段数・幅で伸ばす(M15 2.2年 と M5 5か月、等倍 K=∞ と複利 K=1500/1000、スプレッド2倍)。"""
import numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl4 as sl, tf_rank as r, tf_m5 as m5
import tf_rank_m5 as q
d=r.d; E0=r.E0; YEN=t.YEN; idx=d.o.index
R=r.R; EV=sl.make_events(d,R,None,5.0)
M=q.M
def e5():
    return q.ev5('R + ピラミッディング2段(利確0.5)')
E5=e5()
def cfg(pl,ps,tp=0.5,trail=4): return (0,1,1,pl,ps,1.0,tp,0.3,trail,5.0,0.1,0,0)
GR=[(pl,ps,tp) for pl in (0,2,3,4,6,10) for ps in (1.0,0.7,0.5) for tp in (0.5,) if not(pl==0 and ps!=1.0)]
def pf(tr):
    p=np.array([x[0] for x in tr])*YEN; g=p[p>0].sum(); l=-p[p<0].sum(); return g/l if l>0 else np.nan, p.sum(), len(p)
def maxlot(rr):
    return rr.get('maxlot',np.nan)
def one(a):
    pl,ps,tp=a; c=cfg(pl,ps,tp); o={}
    r0=sl.engine(d.O,d.H,d.L,d.C,EV,c,i0=200); o['pf'],o['pnl'],o['n']=pf(r0['trades'])
    eq=r0['eqa'][200:]*YEN; pk=np.maximum.accumulate(r0['eqc'][200:]*YEN); o['dd1']=(pk-eq).max()
    for K in (1500,1000):
        for lab,spr in (('',None),('s',t.SPR*2)):
            x=sl.engine(d.O,d.H,d.L,d.C,EV,c,i0=200,comp=(E0,K,30),spr=spr); ec=E0+x['eqc'][200:]*YEN; ea=E0+x['eqa'][200:]*YEN; pk=np.maximum.accumulate(ec)
            o[f'c{K}{lab}']=ec[-1]; o[f'd{K}{lab}']=((pk-ea)/pk).max()*100
            y=sl.engine(M.O,M.H,M.L,M.C,E5,c,i0=1,comp=(E0,K,30),spr=spr); ec=E0+y['eqc'][1:]*YEN; ea=E0+y['eqa'][1:]*YEN; pk=np.maximum.accumulate(ec)
            o[f'm{K}{lab}']=ec[-1]; o[f'md{K}{lab}']=((pk-ea)/pk).max()*100
    return dict(pl=pl,ps=ps,tp=tp,**{k:round(v,2) for k,v in o.items()})
if __name__=='__main__':
    with Pool() as pl_: rows=pl_.map(one,GR)
    pd.DataFrame(rows).to_csv('tf_pyrlong.csv',index=False); print('done',len(rows))
