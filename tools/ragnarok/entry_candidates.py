import os
DATA=os.environ.get('RAGNAROK_DATA','data')
import pandas as pd, numpy as np
m=pd.read_csv(DATA+'/M1.csv',header=None,names=['d','tm','o','h','l','c','v'])
m['t']=pd.to_datetime(m.d+' '+m.tm,format='%Y.%m.%d %H:%M'); m=m.set_index('t')
b=pd.read_pickle(DATA+'/baskets.pkl').sort_values('start')
b['end']=[max([L['ct'] for L in legs if 'ct' in L],default=pd.NaT) for legs in b.legs]
# fix: basket end cannot exceed next leg0 of same (g,ty); unknown end -> next start
b['end_fix']=b.end
for (g,ty),x in b.groupby(['g','ty']):
    idx=x.index.tolist()
    for i,j in zip(idx,idx[1:]+[None]):
        nxt=b.loc[j,'start'] if j is not None else m.index[-1]
        e=b.loc[i,'end']
        b.loc[i,'end_fix']= nxt if (pd.isna(e) or e>nxt) else e
b.to_pickle(DATA+'/baskets_fix.pkl')
K={'b':3,'c':11,'a':20}
t0=pd.Timestamp('2026-09-22 10:40'); t1=m.index[-1]
res={}
for g in 'bca':
    k=K[g]; step=5 if g=='a' else 1; out=[]
    for ty,sg in (('buy',1),('sell',-1)):
        x=b[(b.g==g)&(b.ty==ty)]
        busy=pd.Series(False,index=m.index)
        for _,r in x.iterrows():
            busy[(m.index>=r.start.floor('min'))&(m.index<=r.end_fix.floor('min'))]=True
        starts=set(x.start.dt.floor('min'))
        ends=x.end_fix.sort_values()
        for t in m.index[(m.index>=t0)&(m.index<=t1)]:
            ent=t in starts
            if not ent and (busy[t] or (step==5 and t.minute%5)): continue
            ref=t-pd.Timedelta(minutes=k)
            if ref not in m.index: continue
            s=(m.o[t]-m.c[ref])*100*sg
            le=ends[ends<t]; since=(t-le.iloc[-1]).total_seconds()/60 if len(le) else 999
            out.append(dict(t=t,ty=ty,ent=ent,s=s,since=since))
    d=pd.DataFrame(out); d.to_pickle(f'{DATA}/entry2_{g}.pkl')
    for ty in ('buy','sell'):
        z=d[d.ty==ty]; e=z[z.ent]; n=z[(~z.ent)&(z.s>0)]
        print(f'{g} {ty}: entries {len(e)} (s>0: {(e.s>0).sum()})  missed bars with s>0: {len(n)}  (since>=5: {(n.since>=5).sum()})')
