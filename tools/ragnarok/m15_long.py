import pandas as pd, numpy as np
m=pd.read_csv('GOLDmicro15.csv',header=None,names=['d','tm','o','h','l','c','v'])
st=pd.to_datetime(m.d+' '+m.tm,format='%Y.%m.%d %H:%M')
# 米国夏時間(2nd Sun Mar - 1st Sun Nov): サーバーGMT+3 → JST=+6、冬: GMT+2 → JST=+7
def us_dst(ts):
    y=ts.year
    mar=pd.Timestamp(y,3,1); s2=mar+pd.Timedelta(days=(6-mar.dayofweek)%7+7)
    nov=pd.Timestamp(y,11,1); s1=nov+pd.Timedelta(days=(6-nov.dayofweek)%7)
    return s2<=ts<s1
off=st.map(lambda t:6 if us_dst(t) else 7)
m['t']=st+pd.to_timedelta(off,unit='h'); m=m.set_index('t').sort_index()
print('期間(JST)',m.index[0],'〜',m.index[-1],len(m),'本')
# 取引日(JST7:00区切り)
m['tday']=(m.index-pd.Timedelta(hours=7)).normalize()
H=m.index.floor('h').unique()
hi=m.h.values; lo=m.l.values; op=m.o.values; idx=m.index.values
rows=[]
for t in H:
    p=np.searchsorted(idx,t.to_datetime64())
    e3=np.searchsorted(idx,(t+pd.Timedelta(hours=3)).to_datetime64()); e6=np.searchsorted(idx,(t+pd.Timedelta(hours=6)).to_datetime64())
    if e3-p<6: continue
    o=op[p]
    rows.append(dict(t=t,o=o,m3=max(hi[p:e3].max()-o,o-lo[p:e3].min())/o*100,m6=max(hi[p:e6].max()-o,o-lo[p:e6].min())/o*100,
                     m3d=max(hi[p:e3].max()-o,o-lo[p:e3].min())))
d=pd.DataFrame(rows).set_index('t')
d['wd']=d.index.dayofweek; d['hr']=d.index.hour; d['tday']=(d.index-pd.Timedelta(hours=7)).normalize()
d.to_pickle('m15_moves.pkl')
T3,T6=0.70,1.16   # 現在の価格4300で 30ドル / 50ドル に相当
wd=['月','火','水','木','金','土']
pd.set_option('display.width',250)
q=d.pivot_table(index='wd',columns='hr',values='m3',aggfunc=lambda x:(x>=T3).mean()*100); q.index=[wd[i] for i in q.index]
print(f'\n[2.2年] 3時間以内に片方向{T3}%以上(≒現在30ドル)の割合%'); print(q.round(0).fillna(-1).astype(int).to_string())
q=d.pivot_table(index='wd',columns='hr',values='m6',aggfunc=lambda x:(x>=T6).mean()*100); q.index=[wd[i] for i in q.index]
print(f'\n[2.2年] 6時間以内に片方向{T6}%以上(≒現在50ドル)の割合%'); print(q.round(0).fillna(-1).astype(int).to_string())
print('\n曜日別 3h>=0.70% / 6h>=1.16% / 件数')
for i in sorted(d.wd.unique()):
    x=d[d.wd==i]; print(wd[i],round((x.m3>=T3).mean()*100,1),round((x.m6>=T6).mean()*100,1),len(x))
def zone(h):
    if 7<=h<15: return '1東京 7-15'
    if 15<=h<21: return '2欧州 15-21'
    if h>=21 or h<2: return '3NY前半 21-2'
    return '4NY後半 2-7'
d['zone']=d.hr.map(zone)
print('\n時間帯別 3h>=0.70% / 6h>=1.16%')
for z,x in d.groupby('zone'): print(z,round((x.m3>=T3).mean()*100,1),round((x.m6>=T6).mean()*100,1))
# 年ごと(レジーム確認)
d['yq']=d.index.to_period('Q')
print('\n四半期別 3h片方向の中央値(%) / 3h>=0.70%の割合 / 平均価格')
print(d.groupby('yq').agg(med=('m3','median'),r=('m3',lambda x:(x>=T3).mean()*100),px=('o','mean')).round(2).to_string())
# 20-24時 水木金 vs その他
x=d[(d.wd.isin([2,3,4]))&(d.hr>=20)]; y=d[~((d.wd.isin([2,3,4]))&(d.hr>=20))]
print('\n水木金20-24時: 3h>=0.70%',round((x.m3>=T3).mean()*100,1),' 6h>=1.16%',round((x.m6>=T6).mean()*100,1),' / その他',round((y.m3>=T3).mean()*100,1),round((y.m6>=T6).mean()*100,1))
