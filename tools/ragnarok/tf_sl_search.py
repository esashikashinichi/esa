"""解析38: 損切り幅を変えた探索。入口8種 × フィルター4種 × 買い増しの形9 × 利確の形12 × 損切り7(2〜12 ATR)"""
import tf_model as t, tf_sl as sl, numpy as np, pandas as pd, itertools, json
from multiprocessing import Pool
o=t.load_m15(); d=t.Data(o); DAYS=len(set(o.index.date))
P=[np.datetime64(x) for x in ('2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01','2026-09-22')]
IDX=[max(200,int(np.searchsorted(o.index.values,x))) for x in P]; SEGS=list(zip(IDX[:-1],IDX[1:])); CUT=IDX[3]
ENT=['pb_ema','pb_rsi','rsi2','don55','don100','x20_50','macd','adx']
FIL=['none','h4','h1h4','h4adx']
LEG=[(0,1,1,0,1,1),(1,1,1.5,0,1,1),(2,1,1.5,0,1,1),(1,2,1.5,0,1,1),(2,2,1.5,0,1,1),(0,1,1,1,1.0,1.0),(0,1,1,2,1.0,1.0),(0,1,1,2,0.75,0.5),(2,2,1.5,2,1.0,1.0)]
EXT=[]
for tp in (0.5,0.75,1.0,1.5):
    EXT.append((tp,1.0,4))
    for fr in (0.3,0.5): EXT.append((tp,fr,4))
SLS=[2,3,4,5,6,8,12]
def f(a):
    e,fl=a; s=t.apply_filter(d,t.signals(d,e),fl); ev=sl.make_events(d,s); rows=[]
    for lg in LEG:
        for tp,fr,tr in EXT:
            for sv in SLS:
                cfg=lg+(tp,fr,tr,float(sv),0.1)
                r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200)
                F=sl.summarize(r,200,d.N,SEGS,DAYS); A=sl.summarize(r,200,CUT,[(200,CUT)],DAYS); B=sl.summarize(r,CUT,d.N,[(CUT,d.N)],DAYS)
                rows.append(dict(entry=e,filter=fl,nl=lg[0],nstep=lg[1],nmult=lg[2],pl=lg[3],pstep=lg[4],pmult=lg[5],tp=tp,frac=fr,trail=tr,sl=sv,
                    **{k:F[k] for k in ('n','win','pf','pnl','dd','worst','avgw','avgl','sl_pct','epd','open_end','maxlot')},
                    is_n=A['n'],is_pf=A['pf'],is_pnl=A['pnl'],oos_n=B['n'],oos_pf=B['pf'],oos_pnl=B['pnl'],oos_dd=B['dd'],seg_pnl=json.dumps([round(x) for x in F['seg_pnl']])))
    return rows
if __name__=='__main__':
    with Pool(4) as p: R=p.map(f,list(itertools.product(ENT,FIL)),chunksize=1)
    D=pd.DataFrame([r for rr in R for r in rr]); D.to_csv('tf_sl.csv',index=False); print('done',len(D))
