import pandas as pd, numpy as np
m=pd.read_csv('GOLDmicro5.csv',header=None,names=['d','tm','o','h','l','c','v'])
m['t']=pd.to_datetime(m.d+' '+m.tm,format='%Y.%m.%d %H:%M')+pd.Timedelta(hours=6)  # server(UTC+3)->JST
m=m.set_index('t')
print('期間(JST)',m.index[0],'〜',m.index[-1],'本数',len(m))
h=m.resample('1h').agg({'o':'first','h':'max','l':'min','c':'last'}).dropna()
h['rng']=(h.h-h.l)
h['wd']=h.index.dayofweek; h['hr']=h.index.hour
wd=['月','火','水','木','金','土']
# 1) 1時間の値幅が10ドル以上になった割合
p=h.pivot_table(index='wd',columns='hr',values='rng',aggfunc=lambda x:(x>=10).mean()*100)
n=h.pivot_table(index='wd',columns='hr',values='rng',aggfunc='count')
a=h.pivot_table(index='wd',columns='hr',values='rng',aggfunc='mean')
p.index=[wd[i] for i in p.index]; a.index=p.index; n.index=p.index
pd.set_option('display.width',250)
print('\n[1] 1時間足の値幅>=10ドルの割合(%)  列=日本時間の時'); print(p.round(0).fillna(-1).astype(int).to_string())
print('\n平均値幅(ドル)'); print(a.round(1).to_string())
print('\n標本数'); print(n.to_string())
# 2) 3時間で10ドル以上一方向(始値→3時間内の最大逆行)
c=m.c; hi=m.h; lo=m.l
rows=[]
for t in h.index:
    w=m.loc[t:t+pd.Timedelta(minutes=175)]
    if len(w)<20: continue
    o=w.o.iloc[0]
    rows.append(dict(t=t,up=w.h.max()-o,dn=o-w.l.min(),r1=h.loc[t,'rng']))
d=pd.DataFrame(rows).set_index('t'); d['mx']=d[['up','dn']].max(axis=1)
d['wd']=d.index.dayofweek; d['hr']=d.index.hour
q=d.pivot_table(index='wd',columns='hr',values='mx',aggfunc=lambda x:(x>=10).mean()*100); q.index=[wd[i] for i in q.index]
print('\n[2] その時刻から3時間以内に始値から片方向に10ドル以上動いた割合(%)'); print(q.round(0).fillna(-1).astype(int).to_string())
# 曜日別まとめ
print('\n曜日別: 1時間値幅>=10ドルの割合(%) / 平均値幅 / 3時間で片方向10ドル以上(%)')
for i in sorted(h.wd.unique()):
    print(wd[i], round((h[h.wd==i].rng>=10).mean()*100,1), round(h[h.wd==i].rng.mean(),2), round((d[d.wd==i].mx>=10).mean()*100,1), len(h[h.wd==i]))
# 月別推移
h['mon']=h.index.to_period('M')
print('\n月別: 1時間値幅の平均 / >=10ドルの割合'); print(h.groupby('mon').rng.agg(['mean',lambda x:(x>=10).mean()*100]).round(2).to_string())
# 日単位: 10ドル以上の1時間が何回あったか
dd=h.groupby(h.index.date).rng.agg(lambda x:(x>=10).sum())
print('\n1日あたり10ドル以上動いた時間の数: 平均',round(dd.mean(),2),' 0回の日の割合',round((dd==0).mean()*100,1),'%')
h.to_pickle('h1_jst.pkl'); d.to_pickle('mv3h.pkl')
