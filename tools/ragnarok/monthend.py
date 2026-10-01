import pandas as pd, numpy as np
d=pd.read_pickle('m15_moves.pkl')
m=pd.read_csv('GOLDmicro15.csv',header=None,names=['d','tm','o','h','l','c','v'])
st=pd.to_datetime(m.d+' '+m.tm,format='%Y.%m.%d %H:%M')
def us_dst(ts):
    y=ts.year; mar=pd.Timestamp(y,3,1); s2=mar+pd.Timedelta(days=(6-mar.dayofweek)%7+7)
    nov=pd.Timestamp(y,11,1); s1=nov+pd.Timedelta(days=(6-nov.dayofweek)%7); return s2<=ts<s1
m['t']=st+pd.to_timedelta(st.map(lambda t:6 if us_dst(t) else 7),unit='h')
m['tday']=(m.t-pd.Timedelta(hours=7)).dt.normalize()
day=m.groupby('tday').agg(o=('o','first'),h=('h','max'),l=('l','min'),n=('o','size'))
day=day[(day.index.dayofweek<5)&(day.n>=40)]
day['rng']=(day.h-day.l)/day.o*100
g=d.groupby('tday')
day['mx6']=g.m6.max(); day['r3']=g.m3.apply(lambda x:(x>=0.70).mean()*100)
# 分類
day['ym']=day.index.to_period('M')
lab={}
for ym,x in day.groupby('ym'):
    ds=list(x.index)
    if len(ds)<10: continue
    lab[ds[-1]]='M0 月末最終営業日'; lab[ds[-2]]='M-1 月末2日前'
    lab[ds[0]]='S0 月初第1営業日'; lab[ds[1]]='S+1 月初第2営業日'
    lab[ds[2]]='S+2 月初第3営業日'
day['cls']=[lab.get(t,'通常日') for t in day.index]
# 第1金曜(雇用統計)を別枠
day['nfp']=[(t.dayofweek==4 and t.day<=7) for t in day.index]
print('期間',day.index[0].date(),'〜',day.index[-1].date(),'営業日',len(day))
res=day.groupby('cls').agg(日数=('rng','size'),日中値幅中央値=('rng','median'),日中値幅平均=('rng','mean'),
    六h最大片方向の中央値=('mx6','median'),六h片方向116超の日=('mx6',lambda x:(x>=1.16).mean()*100),
    三h片方向070超の時間割合=('r3','mean'))
print(res.round(2).to_string())
# 通常日との比(同じ四半期内で正規化: 各日の値幅 / その月の中央値)
day['rel']=day.rng/day.groupby('ym').rng.transform('median')
day['rel6']=day.mx6/day.groupby('ym').mx6.transform('median')
print('\n月内中央値に対する比(1.0=その月の普通の日)')
print(day.groupby('cls')[['rel','rel6']].agg(['mean','median']).round(2).to_string())
print('\n参考: 第1金曜(雇用統計の日)', round(day[day.nfp].rel.mean(),2), '日数',day.nfp.sum(), ' / その他の金曜', round(day[(day.index.dayofweek==4)&~day.nfp].rel.mean(),2))
# 月末最終営業日が金曜・第1営業日が月曜など重なりを表示
print('\n月末最終営業日×曜日の件数', day[day.cls.str.startswith('M0')].index.dayofweek.value_counts().sort_index().to_dict())
day.to_pickle('days.pkl')
