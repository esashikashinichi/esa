import pandas as pd, numpy as np
import os
DATA=os.environ.get("RAGNAROK_DATA","data")
d=pd.read_csv(DATA+'/ea_monitor.csv',sep=';')
d['t']=pd.to_datetime(d.server_time,format='%Y.%m.%d %H:%M:%S')
d['g']=d.comment.str[0]; d['leg']=d.comment.str.split('_').str[1].astype(int)
cur={}; baskets=[]
def fin(k):
    if k in cur and cur[k]: baskets.append((k,cur[k]))
    cur[k]=[]
for _,r in d.iterrows():
    k=(r.g,r.type)
    if r.event=='OPEN':
        if r.leg==0: fin(k)
        cur.setdefault(k,[]).append(dict(r))
    else:
        for L in cur.get(k,[]):
            if L['ticket']==r.ticket: L['cp']=r.close_price; L['ct']=r.t; L['pf']=r.profit
for k in list(cur): fin(k)
rows=[]
for (g,ty),legs in baskets:
    sgn=1 if ty=='buy' else -1
    lots=np.array([L['lots'] for L in legs]); px=np.array([L['open_price'] for L in legs])
    avg=(lots*px).sum()/lots.sum()
    closed=[L for L in legs if 'cp' in L]
    cp=np.mean([L['cp'] for L in closed]) if closed else np.nan
    rows.append(dict(g=g,ty=ty,start=legs[0]['t'],n=len(legs),nclosed=len(closed),
      lots='/'.join(f"{x:.2f}" for x in lots),avg=round(avg,2),close=round(cp,2),
      tp_pts=round((cp-avg)*sgn*100,1),profit=round(sum(L.get('pf',0) for L in legs),1),
      dur_s=int((max(L['ct'] for L in closed)-legs[0]['t']).total_seconds()) if closed else -1,
      steps=[round((px[i-1]-px[i])*sgn*100) for i in range(1,len(px))],
      gstep=[int(L['grid_step_pts']) for L in legs[1:]],
      gaps=[int((legs[i]['t']-legs[i-1]['t']).total_seconds()) for i in range(1,len(legs))],
      legs=legs))
b=pd.DataFrame(rows).sort_values('start').reset_index(drop=True)
b.to_pickle(DATA+'/baskets.pkl')
if __name__=='__main__':
    pd.set_option('display.width',320); pd.set_option('display.max_colwidth',70); pd.set_option('display.max_rows',300)
    print(b.drop(columns='legs').to_string())
