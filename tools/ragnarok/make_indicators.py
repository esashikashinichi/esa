import os
DATA=os.environ.get('RAGNAROK_DATA','data')
import pandas as pd, numpy as np
m=pd.read_csv(DATA+'/'+os.environ.get('M1FILE','M1.csv'),header=None,names=['d','tm','o','h','l','c','v'])
m['t']=pd.to_datetime(m.d+' '+m.tm,format='%Y.%m.%d %H:%M'); m=m.set_index('t')
def rsi_at(tf, n=14):
    # RSI of tf-minute bars where current bar is partial, evaluated at each M1 close
    out={}
    bars=m.c.resample(f'{tf}min').last().dropna()
    # wilder on completed bars
    for t in m.index:
        cur_start=t.floor(f'{tf}min')
        closes=list(bars[bars.index<cur_start].values[-300:])+[m.c[t]]
        s=pd.Series(closes); dlt=s.diff()
        up=dlt.clip(lower=0); dn=-dlt.clip(upper=0)
        au=up.iloc[1:n+1].mean(); ad=dn.iloc[1:n+1].mean()
        for i in range(n+1,len(s)):
            au=(au*(n-1)+up.iloc[i])/n; ad=(ad*(n-1)+dn.iloc[i])/n
        out[t]=100-100/(1+au/ad) if ad>0 else 100
    return pd.Series(out)
m['rsi5']=rsi_at(5); m['rsi15']=rsi_at(15)
m.to_pickle(DATA+'/M1ind.pkl')
d=pd.read_csv(DATA+'/ea_monitor.csv',sep=';'); d['t']=pd.to_datetime(d.server_time,format='%Y.%m.%d %H:%M:%S')
o=d[(d.event=='OPEN')&(d.t.dt.second<=3)]
x=o.set_index(o.t.dt.floor('min')).join(m[['rsi5','rsi15']],how='inner')
# compare with previous bar close value (entry at start of minute ~ previous close)
print(np.c_[x.rsi_M5.values[:10], x.rsi5.values[:10]])
