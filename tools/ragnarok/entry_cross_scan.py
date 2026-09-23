import os
DATA=os.environ.get('RAGNAROK_DATA','data')
import pandas as pd, numpy as np
m=pd.read_csv(DATA+'/M1.csv',header=None,names=['d','tm','o','h','l','c','v'])
m['t']=pd.to_datetime(m.d+' '+m.tm,format='%Y.%m.%d %H:%M'); m=m.set_index('t')
def stoch(df,k=9,d=3,s=3):
    ll=df.l.rolling(k).min(); hh=df.h.rolling(k).max()
    raw=(df.c-ll)/(hh-ll)*100
    K=raw.rolling(s).mean() if False else ((df.c-ll).rolling(s).sum()/(hh-ll).rolling(s).sum()*100)
    D=K.rolling(d).mean(); return K,D
res={}
tfs={1:m}
for tf in (5,15):
    tfs[tf]=m.resample(f'{tf}min').agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna()
sig={}
for tf,df in tfs.items():
    K,D=stoch(df)
    # value of completed bars; map to M1 bar-open time t: last completed tf bar before t
    sig[f'stoKD_{tf}']=(K-D)
    sig[f'stoK_{tf}']=K-50
    for n in (5,10,20,50):
        sig[f'ma{n}_{tf}']=df.c-df.c.rolling(n).mean()
    for f,s in [(5,20),(10,20),(20,50),(5,10)]:
        sig[f'mx{f}_{s}_{tf}']=df.c.rolling(f).mean()-df.c.rolling(s).mean()
def at(series,tf,t):
    # latest completed bar strictly before t (bar start + tf <= t)
    idx=series.index[series.index+pd.Timedelta(minutes=tf)<=t]
    if len(idx)<2: return np.nan,np.nan
    return series[idx[-1]],series[idx[-2]]
for g in 'bca':
    x=pd.read_pickle(fDATA+'/entry3_{g}.pkl')
    out=[]
    for name,s in sig.items():
        tf=int(name.split('_')[-1])
        tp=fp=0;edges=[];levels=[]
        for _,r in x.iterrows():
            sg=1 if r.ty=='buy' else -1
            cur,prev=at(s,tf,r.t)
            lvl=cur*sg>0; edge=(cur*sg>0) and (prev*sg<=0)
            levels.append(lvl); edges.append(edge)
        x['L']=levels; x['E']=edges
        e=x[x.ent]; n=x[~x.ent]
        out.append((name, e.L.mean(), n.L.mean(), e.E.mean(), n.E.mean()))
    print(f'=== {g}  entries={x.ent.sum()} misses={(~x.ent).sum()}')
    for nm,el,nl,ee,ne in sorted(out,key=lambda z:-(z[3]-z[4])):
        print(f'  {nm:14s} level: entry {el:.2f} miss {nl:.2f} | EDGE: entry {ee:.2f} miss {ne:.2f}')
