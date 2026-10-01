import pandas as pd, numpy as np
m=pd.read_csv('GOLDmicro5.csv',header=None,names=['d','tm','o','h','l','c','v'])
m['t']=pd.to_datetime(m.d+' '+m.tm,format='%Y.%m.%d %H:%M')+pd.Timedelta(hours=6); m=m.set_index('t')
H=m.index.floor('h').unique()
wd=['月','火','水','木','金','土']
rows=[]
hi=m.h.values; lo=m.l.values; op=m.o.values; idx=m.index
pos=np.searchsorted(idx.values,H.values)
for t,p in zip(H,pos):
    end3=np.searchsorted(idx.values,(t+pd.Timedelta(hours=3)).to_datetime64())
    end6=np.searchsorted(idx.values,(t+pd.Timedelta(hours=6)).to_datetime64())
    if end3-p<20: continue
    o=op[p]
    m3=max(hi[p:end3].max()-o,o-lo[p:end3].min()); m6=max(hi[p:end6].max()-o,o-lo[p:end6].min())
    rows.append(dict(t=t,m3=m3,m6=m6))
d=pd.DataFrame(rows).set_index('t'); d['wd']=d.index.dayofweek; d['hr']=d.index.hour
pd.set_option('display.width',250)
for col,th in (('m3',20),('m3',30),('m6',30),('m6',50)):
    q=d.pivot_table(index='wd',columns='hr',values=col,aggfunc=lambda x:(x>=th).mean()*100); q.index=[wd[i] for i in q.index]
    print(f'\n[{col[1]}時間以内に始値から片方向{th}ドル以上] 割合%'); print(q.round(0).fillna(-1).astype(int).to_string())
print('\n曜日別(%): 3h>=20 / 3h>=30 / 6h>=30 / 6h>=50')
for i in sorted(d.wd.unique()):
    x=d[d.wd==i]; print(wd[i],*[round((x[c]>=t).mean()*100,1) for c,t in (('m3',20),('m3',30),('m6',30),('m6',50))])
# 時間帯グループ
def zone(h):
    if 7<=h<15: return '東京 7-15時'
    if 15<=h<21: return '欧州 15-21時'
    if h>=21 or h<2: return 'NY前半 21-2時'
    return 'NY後半 2-7時'
d['zone']=d.hr.map(zone)
print('\n時間帯別(%): 3h>=20 / 3h>=30 / 6h>=30 / 6h>=50 / 3h中央値')
for z,x in d.groupby('zone'): print(z,*[round((x[c]>=t).mean()*100,1) for c,t in (('m3',20),('m3',30),('m6',30),('m6',50))], round(x.m3.median(),1))
# 最大級の値動きトップ10(6h)
top=d.sort_values('m6',ascending=False).head(12)
print('\n6時間の片方向の値動き 上位'); print(top[['m3','m6']].round(1).to_string())
