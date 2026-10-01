"""解析41: ピラミッディングで利益を積み上げる方法。入口は R(RSI2<10 + H4 + ADX)ほか。損切りは最初の建値から 5 ATR(make_events の既定値)。"""
import itertools, sys, numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl3 as sl
from tf_rsibb import sig
o=t.load_m15(); d=t.Data(o); DAYS=len(set(o.index.date))
P5=['2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01','2026-09-22']
IDX=[int(np.searchsorted(o.index.values,np.datetime64(x))) for x in P5]; IDX[0]=200
SEG=list(zip(IDX[:-1],IDX[1:])); HALF=int(np.searchsorted(o.index.values,np.datetime64('2026-01-01')))
def entry(name):
    if name=='R': return t.apply_filter(d,t.signals(d,'rsi2'),'h4adx')
    if name=='EMA': return t.apply_filter(d,t.signals(d,'pb_ema'),'h1h4')
    if name=='rc2': return sig(d,'recross',2,20,2.0)
    if name=='rc14': return sig(d,'recross',14,20,1.5)
EV={}
def ev(name):
    if name not in EV: EV[name]=sl.make_events(d,entry(name))
    return EV[name]
def run(a):
    name,cfg=a; r=sl.engine(d.O,d.H,d.L,d.C,ev(name),cfg,i0=200)
    x=sl.summarize(r,200,d.N,SEG,DAYS); b1=sl.summarize(r,200,HALF,[(200,HALF)],len(set(o.index.date[200:HALF]))); b2=sl.summarize(r,HALF,d.N,[(HALF,d.N)],len(set(o.index.date[HALF:])))
    return dict(ent=name,pl=cfg[3],ps=cfg[4],pm=cfg[5],tp=cfg[6],frac=cfg[7],trail=cfg[8],be=cfg[11],pa=cfg[12],N=x['n'],win=x['win'],pf=x['pf'],pnl=x['pnl'],dd=x['dd'],worst=x['worst'],epd=x['epd'],maxlot=x['maxlot'],
      pf_is=b1['pf'],pf_oos=b2['pf'],pos5=sum(1 for v in x['seg_pnl'] if v>0),seg=[round(v) for v in x['seg_pnl']])
def cfg(pl,ps,pm,tp,frac,trail,be,pa): return (0,1,1,pl,ps,pm,tp,frac,trail,5.0,0.1,be,pa)
if __name__=='__main__':
    base=run(('R',cfg(2,1.0,1.0,0.5,0.3,4,0,0))); print('基準 R 再現:',{k:(round(v,2) if isinstance(v,float) else v) for k,v in base.items() if k in('N','win','pf','pnl','dd','worst','maxlot')})
    grid=[('R',cfg(pl,ps,pm,tp,0.3,tr,be,pa)) for pl,ps,pm,tp,tr,be,pa in itertools.product([2,3,4,6],[0.5,0.75,1.0,1.5],[0.5,1.0,1.5],[0.3,0.5,0.75],[4,6],[0,1],[0,1])]
    with Pool() as p: rows=p.map(run,grid,chunksize=8)
    x=pd.DataFrame(rows); x.to_csv('tf_pyr.csv',index=False); print('全',len(x))
    x['score']=x.pnl/x.dd
    good=x[(x.pf_is>1)&(x.pf_oos>1)&(x.pos5==5)&(x.N>=300)]
    print('--- 前期・後期・5期間すべて良い',len(good),'通り / 損益上位12'); print(good.sort_values('pnl',ascending=False).head(12).drop(columns=['ent','score']).to_string())
    print('--- 損益÷落ち込み上位12'); print(good.sort_values('score',ascending=False).head(12).drop(columns=['ent']).to_string())
    for col in ['pl','ps','pm','tp','trail','be','pa']:
        print('--- 要因別',col); print(good.groupby(col).agg(件数=('pnl','size'),損益中央値=('pnl','median'),落込中央値=('dd','median'),PF中央値=('pf','median'),効率=('score','median')).round(2).to_string())
