import pandas as pd
e=pd.read_csv('ea_mon_new.csv',sep=';'); e['t']=pd.to_datetime(e.server_time,format='%Y.%m.%d %H:%M:%S')
e['g']=e.comment.str.split('_').str[0]
op=e[e.event=='OPEN'].set_index('ticket')
c=e[e.event=='CLOSE'].sort_values('t')
grp=[];cur=None
for _,r in c.iterrows():
    if cur and r.g==cur['g'] and r.type==cur['type'] and (r.t-cur['t1']).total_seconds()<=10:
        cur['rows'].append(r); cur['t1']=r.t
    else:
        cur=dict(g=r.g,type=r.type,t0=r.t,t1=r.t,rows=[r]); grp.append(cur)
out=[]
for gp in grp:
    df=pd.DataFrame(gp['rows']); sg=1 if gp['type']=='buy' else -1
    if len(df)<2: continue
    ot=[op.loc[t,'t'] if t in op.index else pd.NaT for t in df.ticket]
    avg=(df.open_price*df.lots).sum()/df.lots.sum()
    first=df.close_price.iloc[0]
    ot=pd.Series(ot)
    out.append(dict(t=gp['t0'].strftime('%m-%d %H:%M:%S'),g=gp['g'],side=gp['type'],legs=len(df),tp=round((first-avg)*100*sg),
      age_min=round((gp['t0']-ot.min()).total_seconds()/60,1) if ot.notna().all() else None,
      since_last_min=round((gp['t0']-ot.max()).total_seconds()/60,1) if ot.notna().all() else None,pnl=round(df.profit.sum())))
o=pd.DataFrame(out); print(o.to_string())
