import pandas as pd, numpy as np
m=pd.read_csv('m1state.csv',sep=';'); m['t']=pd.to_datetime(m.bar_time,format='%Y.%m.%d %H:%M:%S')
e=pd.read_csv('ea_mon_new.csv',sep=';'); e['t']=pd.to_datetime(e.server_time,format='%Y.%m.%d %H:%M:%S')
e=e[(e.event=='OPEN')&(e.t>=m.t.min())]
e['g']=e.comment.str.split('_').str[0]; e['n']=e.comment.str.split('_').str[1].astype(int)
e['bar']=e.t.dt.floor('min')
rows=[]
mi=m.set_index('t')
for _,r in m.iterrows():
    for g in 'abc':
        for side,sg in (('buy',1),('sell',-1)):
            L=r[f'{g}_{side}_legs']
            if L<1: continue
            last=r[f'{g}_{side}_last_price']; sec=r[f'{g}_{side}_sec_since_last']
            px = r.ask if sg==1 else r.bid
            adv=(last-px)*100*sg
            # events in this bar for this grid/side with n==L
            hit=e[(e.bar==r.t)&(e.g==g)&(e.type==side)&(e.n==L)]
            rows.append(dict(t=r.t,g=g,side=side,sg=sg,L=L,sec=sec,adv=adv,hit=len(hit)>0,
              hit_sec=(hit.t.iloc[0]-r.t).seconds if len(hit) else np.nan,
              d3=r.diff3*sg,d11=r.diff11*sg,d20=r.diff20*sg,
              kd1=(r.m1_stoK9-r.m1_stoD9)*sg, k1=r.m1_stoK9, rsi1=r.m1_rsi14,
              kd5=(r.m5_stoK9-r.m5_stoD9)*sg, k5=r.m5_stoK9, rsi5=r.m5_rsi14,
              pm5=(px-r.m1_ma5)*sg*100, pm10=(px-r.m1_ma10)*sg*100, m510=(r.m1_ma5-r.m1_ma10)*sg*100,
              atr=r.m1_atr14))
d=pd.DataFrame(rows)
d.to_csv('nanpin_minutes.csv',index=False)
el=d[(d.sec>=360)]
print('hits total',d.hit.sum())
pd.set_option('display.width',250)
print(d[d.hit][['t','g','side','L','sec','adv','hit_sec','d3','d11','d20','kd1','k1','kd5','k5','pm5','pm10','m510']].to_string())
