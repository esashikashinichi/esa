import pandas as pd, numpy as np
m=pd.read_csv('m1state.csv',sep=';'); m['t']=pd.to_datetime(m.bar_time,format='%Y.%m.%d %H:%M:%S')
m['close_cur']=m.close1.shift(-1)  # close of this bar
m['open_cur']=m.bid
m['spread']=m.ask-m.bid
e=pd.read_csv('ea_mon_new.csv',sep=';'); e['t']=pd.to_datetime(e.server_time,format='%Y.%m.%d %H:%M:%S')
o=e[e.event=='OPEN'].copy(); o['g']=o.comment.str.split('_').str[0]; o['n']=o.comment.str.split('_').str[1].astype(int)
o=o.sort_values("t")
# rebuild legs per basket chain: for each nanpin, prev leg price/time
res=[]
for _,r in o[(o.n>=1)&(o.t>=m.t.min())].iterrows():
    prev=o[(o.g==r.g)&(o.type==r.type)&(o.n==r.n-1)&(o.t<r.t)].iloc[-1]
    sg=1 if r.type=='buy' else -1
    step=(prev.open_price-r.open_price)*100*sg
    wait=(r.t-prev.t).total_seconds()
    # minutes fully eligible (>=420s at bar open) before fill
    w=m[(m.t>=prev.t+pd.Timedelta(seconds=420))&(m.t<r.t.floor('min'))]
    px=np.where(sg==1,w.ask,w.bid)
    adv=(prev.open_price-px)*100*sg
    body=((w.close_cur-w.open_cur)*sg*100).round()
    blocked=[(t.strftime('%H:%M'),int(a),int(b) if b==b else None) for t,a,b in zip(w.t,adv,body) if a>=110]
    fb=m[m.t==r.t.floor('min')]
    fillbody=((r.bid - fb.bid.iloc[0])*sg*100) if len(fb) else np.nan
    res.append(dict(time=r.t.strftime('%H:%M:%S'),leg=r.comment,side=r.type,wait=int(wait),step=round(step),fill_vs_open=round(fillbody) if fillbody==fillbody else None,blocked=blocked))
for x in res: print(x)
