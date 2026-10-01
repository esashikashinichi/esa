"""Ragnarok 解析34: ロック開始の段の比較(t1)、ランダム探索1,600通り(search2)、上位の5期間検証(robust)。hedge_model_v2.py を hedge2 として読み込む"""
import hedge_model_v2 as hedge2  # noqa

# ===== t1.py =====
import hedge_model_v2 as h, pandas as pd, itertools
from multiprocessing import Pool
def f(a):
    hf,ml=a
    d=h.run('hold',hedge_from=hf,maxlegs=ml,sl=5000); d.update(hedge_from=hf+1,maxlegs_set=ml); return d
if __name__=='__main__':
    cfg=list(itertools.product([1,2,3,4],[8,10,12,15]))
    with Pool(4) as p: rows=p.map(f,cfg)
    for ml in (8,10,12,15):
        d=h.run('none',maxlegs=ml,sl=5000); d.update(hedge_from=0,maxlegs_set=ml); rows.append(d)
    D=pd.DataFrame(rows); D.to_csv('t1.csv',index=False)
    print(D[['hedge_from','maxlegs_set','baskets','pnl','hedge_pnl','max_float','sl']].sort_values(['hedge_from','maxlegs_set']).to_string(index=False))

# ===== search2.py =====
import hedge_model_v2 as h, pandas as pd, random
from multiprocessing import Pool
MID=39196
SP=dict(rule=['none','hold'],hedge_from=[1,2],maxlegs=[3,4,5,6,8,12],mult=[1.0,1.5],step=[1.1,2.0,4.0],tstop=[None,6,24,72],
        bsl=[None,1000,2000],tf=[None,'h1'],kdmin=[0,10],tps=[1.0,1.5],dmax=[None,20])
def f(c):
    kw={k:v for k,v in c.items() if k!='rule'}
    if c['rule']=='none': kw.pop('hedge_from')
    a=h.run(c['rule'],sl=5000,i1=MID,**kw); b=h.run(c['rule'],sl=5000,i0=MID,**kw)
    return dict(**c,pnl1=a['pnl'],dd1=a['max_float'],sl1=a['sl'],n1=a['baskets'],pnl2=b['pnl'],dd2=b['max_float'],sl2=b['sl'],n2=b['baskets'])
if __name__=='__main__':
    r=random.Random(1); seen=set(); cfgs=[]
    while len(cfgs)<1600:
        c={k:r.choice(v) for k,v in SP.items()}
        if c['rule']=='none': c['hedge_from']=0
        key=tuple(sorted((k,str(v)) for k,v in c.items()))
        if key in seen: continue
        seen.add(key); cfgs.append(c)
    with Pool(4) as p: rows=p.map(f,cfgs,chunksize=8)
    pd.DataFrame(rows).to_csv('search2.csv',index=False); print(len(rows))

# ===== robust.py =====
import hedge_model_v2 as h, pandas as pd, numpy as np
from multiprocessing import Pool
D=pd.read_csv('search2.csv'); D['pnl']=D.pnl1+D.pnl2; D['slc']=D.sl1+D.sl2
top=D[(D.pnl1>0)&(D.pnl2>0)&(D.slc==0)].sort_values('pnl',ascending=False).head(12)
cuts=np.linspace(4,h.N,6).astype(int)
def f(c):
    kw={k:(None if (isinstance(v,float) and np.isnan(v)) else v) for k,v in c.items() if k in ['hedge_from','maxlegs','mult','step','tstop','bsl','tf','kdmin','tps','dmax']}
    if c['rule']=='none': kw.pop('hedge_from')
    for k in ('maxlegs','kdmin','hedge_from'):
        if k in kw and kw[k] is not None: kw[k]=int(kw[k])
    full=h.run(c['rule'],sl=5000,**kw)
    parts=[h.run(c['rule'],sl=5000,i0=a,i1=b,**kw)['pnl'] for a,b in zip(cuts[:-1],cuts[1:])]
    return dict(rule=c['rule'],cfg=str(kw),full=full['pnl'],dd=full['max_float'],sl=full['sl'],n=full['baskets'],parts=parts,plus=sum(p>0 for p in parts))
if __name__=='__main__':
    with Pool(4) as p: rows=p.map(f,[r for _,r in top.iterrows()])
    R=pd.DataFrame(rows); R.to_csv('robust.csv',index=False); print(R.to_string(index=False))
