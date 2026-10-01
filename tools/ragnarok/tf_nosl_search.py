"""解析38: 損切り無し。入口10種 × フィルター4種 × 買い増しの形 × 利確の形 を、資金曲線(含み損込み)で比べる"""
import tf_model as t, tf_nosl as ns, numpy as np, pandas as pd, itertools, json
from multiprocessing import Pool
o=t.load_m15(); d=t.Data(o); DAYS=len(set(o.index.date)); BPD=96
P=[np.datetime64(x) for x in ('2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01','2026-09-22')]
IDX=[max(200,int(np.searchsorted(o.index.values,x))) for x in P]; SEGS=list(zip(IDX[:-1],IDX[1:])); CUT=IDX[3]
ENT=['pb_ema','pb_rsi','rsi2','don20','don55','don100','x20_50','x9_21','macd','adx']
FIL=['none','h4','h1h4','h4adx']
LEG=[(0,1,1,0,1,1)]
for nstep in (1,2):
    for nl in (1,2,3):
        for nm in (1.0,1.5): LEG.append((nl,nstep,nm,0,1,1))
for pstep in (0.75,1.5):
    for pl in (1,2):
        for pm in (0.5,1.0): LEG.append((0,1,1,pl,pstep,pm))
for nstep in (1,2):
    for nl,pl in ((2,2),(3,2)): LEG.append((nl,nstep,1.5,pl,1.0,1.0))
EXT=[]
for tp in (0.5,0.75,1.0,1.5,2.0):
    EXT.append((tp,1.0,4))
    for fr in (0.3,0.5):
        for tr in (3,4): EXT.append((tp,fr,tr))
def f(a):
    e,fl=a; s=t.apply_filter(d,t.signals(d,e),fl); ev=ns.make_events(d,s); rows=[]
    for lg in LEG:
        for tp,fr,tr in EXT:
            cfg=lg+(tp,fr,tr)
            r=ns.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200)
            F=ns.summarize(r,200,d.N,SEGS,BPD,DAYS); A=ns.summarize(r,200,CUT,[(200,CUT)],BPD,DAYS); B=ns.summarize(r,CUT,d.N,[(CUT,d.N)],BPD,DAYS)
            rows.append(dict(entry=e,filter=fl,cfg=json.dumps(cfg),nl=lg[0],nstep=lg[1],nmult=lg[2],pl=lg[3],pstep=lg[4],pmult=lg[5],tp=tp,frac=fr,trail=tr,
                **{k:F[k] for k in ('pnl','maxfl','dd','entries','legs','closed','open_end','epd','lpd','maxlot','hold_med','hold_p90','under')},
                is_pnl=A['pnl'],is_maxfl=A['maxfl'],is_dd=A['dd'],oos_pnl=B['pnl'],oos_maxfl=B['maxfl'],oos_dd=B['dd'],
                seg_pnl=json.dumps([round(x,1) for x in F['seg_pnl']]),seg_maxfl=json.dumps([round(x,1) for x in F['seg_maxfl']])))
    return rows
if __name__=='__main__':
    with Pool(4) as p: R=p.map(f,list(itertools.product(ENT,FIL)),chunksize=1)
    D=pd.DataFrame([r for rr in R for r in rr]); D.to_csv('tf_nosl.csv',index=False); print('done',len(D))
