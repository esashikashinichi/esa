import pandas as pd
e=pd.read_csv('ea_mon_new.csv',sep=';'); e['t']=pd.to_datetime(e.server_time,format='%Y.%m.%d %H:%M:%S')
e['g']=e.comment.str.split('_').str[0]
op=e[e.event=='OPEN']; cl=e[e.event=='CLOSE']
opened=dict(zip(op.ticket,op.t)); closed=dict(zip(cl.ticket,cl.t))
first_t=e.t.min()
c=cl.sort_values('t')
grp=[];cur=None
for _,r in c.iterrows():
    if cur and r.type==cur['type'] and (r.t-cur['t1']).total_seconds()<=3:
        cur['rows'].append(r); cur['t1']=r.t
    else:
        cur=dict(type=r.type,t0=r.t,t1=r.t,rows=[r]); grp.append(cur)
# positions known: tickets closed; open time from OPEN if available
for gp in grp:
    df=pd.DataFrame(gp['rows']); sg=1 if gp['type']=='buy' else -1
    # all same-direction positions open just before t0 (from close rows lookup: need open price) 
    allp=cl[(cl.type==gp['type'])&(cl.t>=gp['t0'])]
    allp=allp[[ (opened.get(k,first_t)<gp['t0']) for k in allp.ticket]]
    px=df.close_price.iloc[0]
    def tp(d): 
        a=(d.open_price*d.lots).sum()/d.lots.sum(); return round((px-a)*100*sg)
    grids=sorted(df.g.unique())
    if len(df)<2 and len(allp)==len(df): continue
    s=f"{gp['t0'].strftime('%m-%d %H:%M:%S')} {gp['type']:4s} closed={','.join(grids)} n={len(df)} "
    for g in grids: s+=f"| {g}:tp={tp(df[df.g==g])} "
    s+=f"|| grpTP={tp(df)} ; stillOpenSameDir={len(allp)-len(df)} allDirTP={tp(allp)}"
    print(s)
