import os
DATA=os.environ.get('RAGNAROK_DATA','data')
import pandas as pd, numpy as np
m=pd.read_pickle(DATA+'/M1ind.pkl'); b=pd.read_pickle(DATA+'/baskets.pkl')
bars5=m.c.resample('5min').last().dropna()
def rsi5(t,price,n=14):
    closes=list(bars5[bars5.index<t.floor('5min')].values[-200:])+[price]
    s=pd.Series(closes).diff().iloc[1:]
    up=s.clip(lower=0).values; dn=(-s.clip(upper=0)).values
    au=up[:n].mean(); ad=dn[:n].mean()
    for i in range(n,len(up)): au=(au*(n-1)+up[i])/n; ad=(ad*(n-1)+dn[i])/n
    return 100-100/(1+au/ad)
E=[];W=[]
for _,B in b.iterrows():
    sell=B.ty=='sell'; legs=B.legs
    for i in range(1,len(legs)):
        p,L=legs[i-1],legs[i]
        if int(L['comment'].split('_')[1])!=int(p['comment'].split('_')[1])+1: continue
        te=L['t'].floor('min')
        if te>m.index[-1]: continue
        r=rsi5(L['t'],L['bid']); E.append((sell,r,L['comment'],L['t'],round(L['rsi_M5'],1)))
        t0=p['t']+pd.Timedelta(seconds=420)
        for tt in m.loc[t0.ceil('min'):te-pd.Timedelta(minutes=1)].index:
            bar=m.loc[tt]
            if sell and bar.l < p['bid']+1: continue
            if (not sell) and bar.h > p['bid']-1: continue
            # most favourable RSI reached in the bar (sell: lowest price -> lowest RSI)
            W.append((sell,rsi5(tt,bar.l if sell else bar.h),L['comment'],tt))
for side in (True,False):
    e=sorted(round(x[1],1) for x in E if x[0]==side); w=sorted(round(x[1],1) for x in W if x[0]==side)
    print('SELL' if side else 'BUY','entries RSI5:',e); print('   waits (best RSI in bar):',w)
print([ (x[2],x[3].strftime('%H:%M:%S'),round(x[1],1),x[4]) for x in E if x[0]][:40])
