import pandas as pd, numpy as np
m=pd.read_csv('m1state.csv',sep=';'); m['t']=pd.to_datetime(m.bar_time,format='%Y.%m.%d %H:%M:%S')
m=m.sort_values('t').reset_index(drop=True)
# ensure consecutive minutes
m['gap']=m.t.diff().dt.total_seconds()
e=pd.read_csv('ea_mon_new.csv',sep=';'); e['t']=pd.to_datetime(e.server_time,format='%Y.%m.%d %H:%M:%S')
o=e[(e.event=='OPEN')&e.comment.str.endswith('_0')&(e.t>=m.t.min())].copy()
o['g']=o.comment.str[0]; o['bar']=o.t.dt.floor('min'); o['sg']=np.where(o.type=='buy',1,-1)
feats={}
kd=np.sign(m.m1_stoK9-m.m1_stoD9); feats['sto9x']=kd*(kd!=kd.shift())
kd5=np.sign(m.m1_stoK5-m.m1_stoD5); feats['sto5x']=kd5*(kd5!=kd5.shift())
x=np.sign(m.m1_ma5-m.m1_ma10); feats['ma5_10x']=x*(x!=x.shift())
x=np.sign(m.m1_ma10-m.m1_ma20); feats['ma10_20x']=x*(x!=x.shift())
x=np.sign(m.m1_ma5-m.m1_ma20); feats['ma5_20x']=x*(x!=x.shift())
x=np.sign(m.close1-m.m1_ma5); feats['c_ma5x']=x*(x!=x.shift())
x=np.sign(m.close1-m.m1_ma10); feats['c_ma10x']=x*(x!=x.shift())
x=np.sign(m.close1-m.m1_ma20); feats['c_ma20x']=x*(x!=x.shift())
x=np.sign(m.m1_rsi14-50); feats['rsi50x']=x*(x!=x.shift())
x=np.sign(m.m5_stoK9-m.m5_stoD9); feats['m5sto9x']=x*(x!=x.shift())
F=pd.DataFrame(feats); F['t']=m.t
for g in 'bc':
    og=o[(o.g==g)&(o.t-o.bar<=pd.Timedelta('5s'))]
    print(f'--- grid {g}: first entries at bar open n={len(og)}')
    for f in feats:
        col=F.set_index('t')[f]
        hit=sum(col.get(b,0)==s for b,s in zip(og.bar,og.sg))
        # also within previous 1..2 bars
        hit2=sum(any(col.get(b-pd.Timedelta(minutes=k),0)==s for k in range(0,3)) for b,s in zip(og.bar,og.sg))
        tot=(col!=0).sum()
        print(f'{f:10s} same-bar match {hit}/{len(og)}  within0-2bars {hit2}/{len(og)}  total crosses {tot}')
print('--- base rate: random bars, direction=sign(diff3)')
sgn=np.sign(m.diff3).values
col=F['c_ma5x'].values
ok=[any(col[i-k]==sgn[i] for k in range(3)) for i in range(3,len(m)) if sgn[i]!=0]
print('c_ma5x within0-2 base', np.mean(ok))
col=F['sto9x'].values
print('sto9x same-bar base', np.mean([col[i]==sgn[i] for i in range(3,len(m)) if sgn[i]!=0]))
print('--- window scan c_ma5x / c_ma10x')
idx={t:i for i,t in enumerate(m.t)}
for f in ['c_ma5x','c_ma10x','sto9x','sto5x']:
  col=F[f].values
  for W in (1,2,3,4):
    base=np.mean([any(col[i-k]==sgn[i] for k in range(W)) for i in range(5,len(m)) if sgn[i]!=0])
    for g in 'bc':
        og=o[(o.g==g)&(o.t-o.bar<=pd.Timedelta('5s'))]
        h=sum(any(col[idx[b]-k]==s for k in range(W)) for b,s in zip(og.bar,og.sg) if b in idx)
        print(f,W,g,f'{h}/{len(og)}',f'base {base:.2f}')
print('--- precision test b: cross of close1 vs ma5 at row t-k')
col=F['c_ma5x'].values
og=o[(o.g=='b')&(o.t-o.bar<=pd.Timedelta('5s'))]
ent={(b,s) for b,s in zip(og.bar,og.sg)}
for k in (0,1):
    h=sum(col[idx[b]-k]==s for b,s in ent if b in idx); 
    cand=0;hit=0;miss=[]
    for i in range(2,len(m)-1):
        s=col[i-k]
        if s==0: continue
        side='buy' if s==1 else 'sell'
        if m.loc[i,f'b_{side}_legs']>0: continue
        cand+=1
        if (m.t[i],s) in ent: hit+=1
        else: miss.append(m.t[i].strftime('%H:%M')+side[0])
    print(f'k={k}: entries matched {h}/{len(ent)} ; candidate bars(no b basket that side)={cand} entered={hit}')
    if k==1: print('non-entered examples',miss[:40])
