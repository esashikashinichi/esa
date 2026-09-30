"""Ragnarok 解析32: b の初弾 — ストキャスの計算方法を変えた再検証(公開デモ口座 09-28〜09-30)

入力(同じフォルダ): events.csv(demo_ea_monitor_events_v38.csv)、m1ohlc.csv、fire_b.pkl(b_fire_conditions.py の1で作成)、
                   ../real/events_v38.csv(本番 09-28)
1. ストキャス 6,912通り(期間3〜14 × スロー1〜5 × %D 2〜5 × MA 4種 × 価格 Low/High・Close/Close × 形成中/確定足 × スローの方式 合計比/平均)
2. クロス型の条件と決定木
3. 条件のそろった足で、本番とデモが同じ足で入るか
4. 実際の約定 bid でストキャスを計算し直す
"""
import pandas as pd,numpy as np,itertools
from sklearn.metrics import roc_auc_score
o=pd.read_csv('m1ohlc.csv'); o['t']=pd.to_datetime(o.Date+' '+o.Time,format='%Y.%m.%d %H:%M'); o=o.set_index('t').sort_index()
R=pd.read_pickle('fire_b.pkl'); E=R[(~R.open_basket)&(R.since>=240)].copy()
s=np.where(E.side=='buy',1,-1); f=E.fired.values
C,O,H,L=o.Close,o.Open,o.High,o.Low
mom3=O-C.shift(3)
def age_arr():
    out=[]
    for t,r in E.iterrows():
        sg=1 if r.side=='buy' else -1; c=(sg*mom3>0); i=c.index.get_loc(t); n=0
        while i-1-n>=0 and c.iloc[i-1-n]: n+=1
        out.append(n)
    return np.array(out)
age=age_arr()
def ma_live(closedK,liveK,n,m):
    # closedK: series of closed-bar values (index t = value of bar t); live value for bar t uses closed up to t-1
    if m=='sma': return (liveK+closedK.shift(1).rolling(n-1).sum())/n if n>1 else liveK
    if m in('ema','smma'):
        a=2/(n+1) if m=='ema' else 1/n
        prev=closedK.ewm(alpha=a,adjust=False).mean().shift(1); return prev+a*(liveK-prev)
    if m=='lwma':
        w=np.arange(1,n+1); tot=liveK*n
        for j in range(1,n): tot=tot+closedK.shift(j)*(n-j)
        return tot/w.sum()
def closed_ma(x,n,m):
    if m=='sma': return x.rolling(n).mean()
    if m=='ema': return x.ewm(span=n,adjust=False).mean()
    if m=='smma': return x.ewm(alpha=1/n,adjust=False).mean()
    return x.rolling(n).apply(lambda v:np.dot(v,np.arange(1,n+1))/np.arange(1,n+1).sum(),raw=True)
def sto(k,sl,d,m,pf,live=True,slowmode='sum'):
    hi=H if pf=='lh' else C; lo=L if pf=='lh' else C
    num_c=C-lo.rolling(k).min(); den_c=hi.rolling(k).max()-lo.rolling(k).min()
    Hl=pd.concat([hi.shift(1).rolling(k-1).max(),O],axis=1).max(axis=1) if k>1 else O
    Ll=pd.concat([lo.shift(1).rolling(k-1).min(),O],axis=1).min(axis=1) if k>1 else O
    num_l=O-Ll; den_l=Hl-Ll
    if slowmode=='sum':
        Kc=100*num_c.rolling(sl).sum()/den_c.rolling(sl).sum()
        Kl=100*(num_l+(num_c.shift(1).rolling(sl-1).sum() if sl>1 else 0))/(den_l+(den_c.shift(1).rolling(sl-1).sum() if sl>1 else 0))
    else: # fast K then SMA
        fc=100*num_c/den_c; fl=100*num_l/den_l
        Kc=fc.rolling(sl).mean(); Kl=(fl+(fc.shift(1).rolling(sl-1).sum() if sl>1 else 0))/sl
    if not live: return Kc.shift(1),closed_ma(Kc,d,m).shift(1)
    return Kl,ma_live(Kc,Kl,d,m)
res=[]
idx=E.index
for k,sl,d,m,pf,live,sm in itertools.product(range(3,15),(1,2,3,4,5),(2,3,4,5),('sma','ema','smma','lwma'),('lh','cc'),(True,False),('sum','sma')):
    if sl==1 and sm=='sma': continue
    K,D=sto(k,sl,d,m,pf,live,sm)
    Kv=K.reindex(idx).values; Dv=D.reindex(idx).values
    kd=(Kv-Dv)*s; kk=np.where(s>0,Kv,100-Kv)
    kd=np.nan_to_num(kd); kk=np.nan_to_num(kk,nan=50)
    base=age<=2
    cov=((kd>0)&base)[f].mean()
    # best K band keeping all fires
    kf=kk[f&base&(kd>0)]
    lo_,hi_=(kf.min(),kf.max()) if len(kf) else (0,100)
    m_=base&(kd>0)&(kk>=lo_)&(kk<=hi_)
    res.append(dict(k=k,sl=sl,d=d,m=m,pf=pf,live=live,slow=sm,auc=roc_auc_score(f,kd),cov=cov,
       kd_cov=(kd[f]>0).mean(),n=m_.sum(),fired=(m_&f).sum(),prec=(m_&f).sum()/max(m_.sum(),1),klo=lo_,khi=hi_))
D=pd.DataFrame(res); D.to_pickle('sto_scan.pkl')
print(len(D))
print(D.sort_values('auc',ascending=False).head(20).round(3).to_string())
print(D[D.kd_cov>=0.99].sort_values('prec',ascending=False).head(20).round(3).to_string())

# ---- 2. クロス型の条件と決定木 ----
from sklearn.tree import DecisionTreeClassifier,export_text
from sklearn.model_selection import cross_val_score
def feats(k,sl,d,m,pf,live,sm):
    K,D=sto(k,sl,d,m,pf,live,sm); Kc,Dc=sto(k,sl,d,m,pf,False,sm)
    g=lambda x:x.reindex(E.index).values
    kd=(g(K)-g(D))*s; kd1=(g(Kc)-g(Dc))*s  # previous closed bar
    Kc2,Dc2=Kc.shift(1),Dc.shift(1); kd2=(g(Kc2)-g(Dc2))*s
    kk=np.where(s>0,g(K),100-g(K)); kk1=np.where(s>0,g(Kc),100-g(Kc))
    return np.nan_to_num(kd),np.nan_to_num(kd1),np.nan_to_num(kd2),np.nan_to_num(kk,nan=50),np.nan_to_num(kk1,nan=50)
for cfg in [(4,3,3,'sma','lh',True,'sum'),(4,2,2,'sma','cc',False,'sum'),(5,3,2,'sma','cc',True,'sum'),(5,3,3,'sma','lh',True,'sum'),(9,3,3,'sma','lh',True,'sum')]:
    kd,kd1,kd2,kk,kk1=feats(*cfg); b=age<=2
    print('====',cfg)
    for nm,mk in [('K>D',kd>0),('cross now(prev<=0)',(kd>0)&(kd1<=0)),('cross within2',(kd>0)&((kd1<=0)|(kd2<=0))),('kd rising',(kd>kd1)),('K>D & rising',(kd>0)&(kd>kd1)),('K rising',kk>kk1),('K>D & K rising',(kd>0)&(kk>kk1))]:
        m=b&mk; print(f'  {nm:22s} 成立{m.sum():4d} 入った{(m&f).sum():3d} 再現{(m&f).sum()/f.sum():.2f} 精度{(m&f).sum()/max(m.sum(),1):.2f}')
    X=np.c_[age,kd,kd1,kd2,kk,kk1,kk-kk1]
    for dep in (2,3,4):
        dt=DecisionTreeClassifier(max_depth=dep,min_samples_leaf=8,class_weight='balanced',random_state=0)
        print('  tree',dep,'AUC',cross_val_score(dt,X,f,cv=5,scoring='roc_auc').mean().round(3))
    dt=DecisionTreeClassifier(max_depth=3,min_samples_leaf=8,random_state=0).fit(X,f)
    print(export_text(dt,feature_names=['age','kd','kd1','kd2','K','K1','dK']))

# ---- 3. 本番とデモの一致 ----
K,D=sto(4,3,3,'sma','lh',True,'sum')
kd=np.nan_to_num((K.reindex(E.index).values-D.reindex(E.index).values)*s); kk=np.where(s>0,K.reindex(E.index),100-K.reindex(E.index))
cond=(age<=2)&(kd>0)&(kk>40)&(kk<97)
r=pd.read_csv('../real/events_v38.csv',sep=';'); r['t']=pd.to_datetime(r.time,format='%Y.%m.%d %H:%M:%S')
re=r[(r.event=='ENTRY')&(r.logic=='b')]
rset={(x.side,x.t.floor('min')) for x in re.itertuples() if x.t.second<=5}
t0,t1=re.t.min().floor('min'),re.t.max()
sel=(E.index>=t0)&(E.index<=t1)&cond
T=pd.DataFrame({'demo':f[sel],'real':[(sd,t) in rset for sd,t in zip(E.side[sel],E.index[sel])]})
print(pd.crosstab(T.demo,T.real))
# also: demo non-fired cond bars -> demo fired within next 1-3 min same side?
nxt=[]
en=set(zip(E.side[E.fired],E.index[E.fired]))
for sd,t,fi in zip(E.side[cond],E.index[cond],f[cond]):
    if fi: continue
    nxt.append(any((sd,t+pd.Timedelta(minutes=j)) in en for j in (1,2,3)))
print('not fired cond bars, fired within 3 min after:',np.mean(nxt),len(nxt))

# ---- 4. 約定 bid での再計算 ----
e=pd.read_csv('events.csv',sep=';'); e['t']=pd.to_datetime(e.time,format='%Y.%m.%d %H:%M:%S')
x=e[(e.event=='ENTRY')&(e.logic=='b')&(e.t.dt.second<=5)].copy(); x['bar']=x.t.dt.floor('min')
def sto_at(price,t,k,sl,d,pf='lh'):
    i=o.index.get_loc(t); h=o.High.values; l=o.Low.values; c=o.Close.values
    hi=h if pf=='lh' else c; lo=l if pf=='lh' else c
    Ks=[]
    for j in range(d+sl):  # compute K for bars i-j
        pass
    def raw(b,cur):
        if b==i:
            H_=max(hi[i-k+1:i].max(),cur) if k>1 else cur; L_=min(lo[i-k+1:i].min(),cur) if k>1 else cur; return cur-L_,H_-L_
        return c[b]-lo[b-k+1:b+1].min(), hi[b-k+1:b+1].max()-lo[b-k+1:b+1].min()
    def K(b):
        n=dd=0
        for q in range(sl): a,bb=raw(b-q,price); n+=a; dd+=bb
        return 100*n/dd if dd else 50
    Kv=[K(i-j) for j in range(d)]
    return Kv[0],np.mean(Kv)
rows=[]
for r in x.itertuples():
    sg=1 if r.side=='buy' else -1
    for price,nm in ((r.bid,'bid'),(o.Open[r.bar],'open')):
        k_,d_=sto_at(price,r.bar,4,3,3)
        kd=(k_-d_)*sg; kk=k_ if sg>0 else 100-k_
        m3=(price-o.Close.shift(3)[r.bar])*sg
        rows.append(dict(t=r.t,nm=nm,kd=kd,K=kk,m3=m3,sec=r.t.second))
Z=pd.DataFrame(rows).pivot_table(index='t',columns='nm',values=['kd','K','m3'])
print(Z.describe().round(1).to_string())
print('kd<=0 open',(Z['kd']['open']<=0).sum(),' bid',(Z['kd']['bid']<=0).sum())
print('m3<=0 open',(Z['m3']['open']<=0).sum(),' bid',(Z['m3']['bid']<=0).sum())
