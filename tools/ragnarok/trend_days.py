# トレンド日(12時間以内に片方向1.8%以上 ≒ 現在価格で80ドル)の頻度。monthend.py の days.pkl を使う
import pandas as pd, numpy as np
days=pd.read_pickle('days.pkl')
m=pd.read_csv('GOLDmicro15.csv',header=None,names=['d','tm','o','h','l','c','v'])
st=pd.to_datetime(m.d+' '+m.tm,format='%Y.%m.%d %H:%M')
def us_dst(ts):
    y=ts.year; mar=pd.Timestamp(y,3,1); s2=mar+pd.Timedelta(days=(6-mar.dayofweek)%7+7)
    nov=pd.Timestamp(y,11,1); s1=nov+pd.Timedelta(days=(6-nov.dayofweek)%7); return s2<=ts<s1
m['t']=st+pd.to_timedelta(st.map(lambda t:6 if us_dst(t) else 7),unit='h'); m=m.set_index('t').sort_index()
idx=m.index.values; hi=m.h.values; lo=m.l.values; op=m.o.values
H=m.index.floor('h').unique(); rows=[]
for t in H:
    p=np.searchsorted(idx,t.to_datetime64()); e=np.searchsorted(idx,(t+pd.Timedelta(hours=12)).to_datetime64())
    if e-p<24: continue
    o=op[p]; rows.append((t,max(hi[p:e].max()-o,o-lo[p:e].min())/o*100))
d=pd.DataFrame(rows,columns=['t','m12']).set_index('t'); d['tday']=(d.index-pd.Timedelta(hours=7)).normalize()
days['m12']=d.groupby('tday').m12.max()
days['trend']=days.m12>=1.8
print('トレンド日: 全体',round(days.trend.mean()*100,1),'% /',days.trend.sum(),'日 /',len(days),'日')
wd=['月','火','水','木','金']
print('曜日別',{wd[i]:round(days[days.index.dayofweek==i].trend.mean()*100,1) for i in range(5)})
print('月末月初別'); print(days.groupby('cls').trend.agg(['mean','sum','size']).assign(mean=lambda x:(x['mean']*100).round(1)).to_string())
days['q']=days.index.to_period('Q'); print(days.groupby('q').trend.mean().mul(100).round(1).to_string())
