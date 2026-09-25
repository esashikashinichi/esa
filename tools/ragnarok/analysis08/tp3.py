import pandas as pd
m=pd.read_csv('m1state.csv',sep=';'); m['t']=pd.to_datetime(m.bar_time,format='%Y.%m.%d %H:%M:%S')
cases=[('10:56:35','c','buy'),('11:30:06','b','sell'),('12:24:07','c','buy'),('13:35:23','b','sell'),('14:01:55','b','buy'),('14:18:31','b','sell'),('15:21:33','b','sell'),('18:45:45','b','buy'),('09:57:38','b','sell'),
       ('10:58:29','b','sell'),('12:18:29','b','sell'),('12:46:22','c','sell'),('14:18:03','c','sell'),('14:45:31','b','buy'),('15:59:38','b','buy'),('13:03:21','b','buy')]
for ts,g,side in cases:
    t=pd.Timestamp('2026-09-23 '+ts); sg=1 if side=='buy' else -1
    w=m[(m.t<t)&(m.t>=t-pd.Timedelta('3h'))]
    w=w[w[f'{g}_{side}_legs']>=2]
    # contiguous tail
    if len(w)==0: print(ts,g,side,'no rows'); continue
    px=w.bid if sg==1 else w.ask
    prof=((px-w[f'{g}_{side}_avg'])*100*sg)
    legs=w[f'{g}_{side}_legs']
    last=w.t.iloc[-1]
    # only rows since legs reached current count
    L=legs.iloc[-1]; sel=legs==L
    print(f"{ts} {g} {side} legs={L} rows={sel.sum()} maxProfitPts(bar-open)={prof[sel].max():.0f} lastRowProfit={prof.iloc[-1]:.0f} path={[int(x) for x in prof[sel].tail(8)]}")
