"""Ragnarok 解析31: b の初弾の発火条件(公開デモ口座 09-28〜09-30)

入力(同じフォルダ): events.csv(demo_ea_monitor_events_v38.csv)、m1ohlc.csv(GOLD_M1_20260928〜30.csv を連結)
1. 候補: M1 足の始値ごとに、方向(始値 − 3本前の終値)の側で、同じ方向の b の束が無く、前の b 初弾から4分以上。
2. 各足の指標(M1/M5/M15 のストキャス・RSI・MA・MACD・CCI・BB 等)を計算し、入った足と入らない足を比較。
3. 形成中の足の M1 ストキャス(4,3,3) と、方向の転換からの本数で必要条件を作る。
"""
# ---- 1. 候補の作成 ----
import pandas as pd, numpy as np
o=pd.read_csv('m1ohlc.csv'); o['t']=pd.to_datetime(o.Date+' '+o.Time,format='%Y.%m.%d %H:%M')
o=o.set_index('t').sort_index()
e=pd.read_csv('events.csv',sep=';'); e['t']=pd.to_datetime(e.time,format='%Y.%m.%d %H:%M:%S')
L='b'
en=e[(e.event=='ENTRY')&(e.logic==L)]; cl=e[(e.event=='BASKET_CLOSE')&(e.logic==L)]
bk=en[['side','basket','t']].merge(cl[['side','basket','t']],on=['side','basket'],how='left',suffixes=('','_c'))
allent=e[e.event.isin(['ENTRY','NANPIN','BASKET_CLOSE'])].t.sort_values().values
C=o.Close; O=o.Open; H=o.High; Lo=o.Low
def rsi(s,p):
    d=s.diff(); a=d.clip(lower=0).ewm(alpha=1/p,adjust=False).mean(); b=(-d).clip(lower=0).ewm(alpha=1/p,adjust=False).mean(); return 100*a/(a+b)
F=pd.DataFrame(index=o.index)
# features known at open of bar t (use shift(1) for closed-bar values)
for k in (1,2,3,5,11,20): F[f'mom{k}']=O-C.shift(k)          # open now vs close k bars back
for p in (5,9,14): F[f'rsi{p}']=rsi(C,p).shift(1)
for p in (5,10,20): F[f'ma{p}d']=O-C.rolling(p).mean().shift(1)
hh=H.rolling(9).max(); ll=Lo.rolling(9).min(); K=100*(C-ll)/(hh-ll); D=K.rolling(3).mean()
F['stoK']=K.shift(1); F['stoKD']=(K-D).shift(1)
F['body1']=(C-O).shift(1); F['body2']=(C-O).shift(2); F['rng1']=(H-Lo).shift(1)
F['gap']=O-C.shift(1)
F['hi5']=O-H.rolling(5).max().shift(1); F['lo5']=O-Lo.rolling(5).min().shift(1)
F['hi15']=O-H.rolling(15).max().shift(1); F['lo15']=O-Lo.rolling(15).min().shift(1)
F['atr14']=(H-Lo).rolling(14).mean().shift(1)
up=(C>O).astype(int); F['ups3']=up.rolling(3).sum().shift(1)
# M5
o5=o.resample('5min').agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
r5=rsi(o5.Close,14); F['m5rsi_c']=r5.shift(1).reindex(F.index,method='ffill')
F['min']=F.index.minute; F['m5pos']=F.index.minute%5; F['hour']=F.index.hour
rows=[]
start,end=en.t.min().floor('min'),en.t.max().ceil('min')
lastent={'buy':pd.Timestamp(0),'sell':pd.Timestamp(0)}
ent_by={(r.side,r.t.floor('min')):r.t for r in en.itertuples() if r.t.second<=5}
for t in F.loc[start:end].index:
    act=allent[(allent>=np.datetime64(t-pd.Timedelta(minutes=40)))&(allent<np.datetime64(t+pd.Timedelta(minutes=40)))]
    if len(act)==0: continue
    m3=F.at[t,'mom3']
    if pd.isna(m3) or m3==0: continue
    side='buy' if m3>0 else 'sell'
    openb=bk[(bk.side==side)&(bk.t<t)&((bk.t_c.isna())|(bk.t_c>t))]
    prev=en[(en.side==side)&(en.t<t)].t
    since=(t-prev.max()).total_seconds() if len(prev) else 9e9
    fired=(side,t) in ent_by
    rows.append(dict(t=t,side=side,open_basket=len(openb)>0,since=since,fired=fired))
R=pd.DataFrame(rows).set_index('t').join(F)
R.to_pickle('fire_b.pkl')
print('candidates',len(R),'fired',R.fired.sum(),' of b entries (sec<=5)',len(ent_by),' total b entries',len(en))
print('fired with open basket:',R[R.fired].open_basket.sum())
print('since dist for fired(min):',(R[R.fired].since/60).describe().round(2).to_dict())

# ---- 2. 形成中の足のストキャス ----
import pandas as pd,numpy as np
o=pd.read_csv('m1ohlc.csv'); o['t']=pd.to_datetime(o.Date+' '+o.Time,format='%Y.%m.%d %H:%M'); o=o.set_index('t').sort_index()
def sto_live(k,sl,d):
    pnum=(o.Close-o.Low.rolling(k).min()); pden=(o.High.rolling(k).max()-o.Low.rolling(k).min())
    H=pd.concat([o.High.shift(1).rolling(k-1).max(),o.Open],axis=1).max(axis=1); L=pd.concat([o.Low.shift(1).rolling(k-1).min(),o.Open],axis=1).min(axis=1)
    num=o.Open-L; den=H-L
    N=num+(pnum.shift(1).rolling(sl-1).sum() if sl>1 else 0); Dn=den+(pden.shift(1).rolling(sl-1).sum() if sl>1 else 0)
    K=100*N/Dn; pK=100*pnum.rolling(sl).sum()/pden.rolling(sl).sum()
    D=(K+pK.shift(1).rolling(d-1).sum())/d
    pD=pK.rolling(d).mean()
    return K,D,pK.shift(1),pD.shift(1)

# ---- 3. 必要条件の評価 ----
R=pd.read_pickle('fire_b.pkl'); E=R[(~R.open_basket)&(R.since>=240)].copy()
_sg=np.where(E.side=='buy',1,-1)
X=pd.DataFrame({'fired':E.fired,'mom11':E.mom11*_sg,'m1_ma10':E.ma10d*_sg,'mom3':E.mom3*_sg},index=E.index)
K,D,pK,pD=sto_live(4,3,3)
C=o.Close; mom3=o.Open-C.shift(3)
def age(ser):
    out=[]
    for t,r in E.iterrows():
        c=ser[r.side]; i=c.index.get_loc(t); n=0
        while i-1-n>=0 and c.iloc[i-1-n]: n+=1
        out.append(n)
    return np.array(out)
st={sd:(sg*mom3>0) for sd,sg in (('buy',1),('sell',-1))}
E['age_st']=age(st)
s=np.where(E.side=='buy',1,-1)
E['kd']=(K-D).reindex(E.index).values*s; E['k']=np.where(s>0,K.reindex(E.index),100-K.reindex(E.index))
E['mom11']=X.mom11; E['ma10']=X.m1_ma10; E['mom3o']=X.mom3
f=E.fired
def ev(n,m):
    tp=(m&f).sum(); c=m.sum(); print(f'{n:58s} 成立{c:4d} 入った{tp:3d} 精度{tp/max(c,1):.2f} 再現{tp/f.sum():.2f}')

ev('A 方向(3本前比)が2本以内に転換',E.age_st<=2)
ev('A & K>D(M1 Stoch4,3,3 形成中)',(E.age_st<=2)&(E.kd>0))
m=(E.age_st<=2)&(E.kd>0)&(E.k>40)&(E.k<97)
ev('A & K>D & 40<K<97',m)
for T in (5,10,15,20): ev(f'  & K-D>{T}',m&(E.kd>T))
