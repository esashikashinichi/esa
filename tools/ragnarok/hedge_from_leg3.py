"""【注意 10-01】このスクリプトはロットの丸めに誤りがあり(0.01×1.5を0.01に丸め続け、ナンピンのロットが増えない)、期間末の含み損も入れていない。正しい版は hedge_model_v2.py(解析34)。
Ragnarok 解析33: b 型 + 3段目からのヘッジ(同ロットの反対売買)のバックテスト(M1 足)

入力: ../data/M1_long.csv(GOLD M1 2026-07-17〜09-23)、../d38/m1ohlc.csv(09-28〜09-30)
実行: python hedge_from_leg3.py(前半の表)、python -c "import hedge_from_leg3 as h; h.more()"(後半の表)
"""
import pandas as pd, numpy as np, sys
SP=0.55; YEN=1.576  # 0.01ロットで1ドル=約1.58円 → 1ロット=157.6円
def load():
    a=pd.read_csv('../data/M1_long.csv',header=None,names=['D','T','O','H','L','C','V'])
    b=pd.read_csv('../d38/m1ohlc.csv'); b.columns=['D','T','O','H','L','C','V']
    d=pd.concat([a,b]); d['t']=pd.to_datetime(d['D']+' '+d['T'],format='%Y.%m.%d %H:%M')
    return d.drop_duplicates('t').set_index('t').sort_index()
o=load()
O,H,L,C=o.O.values,o.H.values,o.L.values,o.C.values; N=len(o); tt=o.index
# 形成中ストキャス(4,3,3) 始値時点
def sto_live():
    s=pd.DataFrame({'H':o.H,'L':o.L,'C':o.C,'O':o.O})
    pn=(s.C-s.L.rolling(4).min()); pd_=(s.H.rolling(4).max()-s.L.rolling(4).min())
    Hl=pd.concat([s.H.shift(1).rolling(3).max(),s.O],axis=1).max(axis=1); Ll=pd.concat([s.L.shift(1).rolling(3).min(),s.O],axis=1).min(axis=1)
    K=100*((s.O-Ll)+pn.shift(1).rolling(2).sum())/((Hl-Ll)+pd_.shift(1).rolling(2).sum())
    Kc=100*pn.rolling(3).sum()/pd_.rolling(3).sum()
    D=(K+Kc.shift(1).rolling(2).sum())/3
    return K.values,D.values
K,D=sto_live()
mom3=O-np.r_[np.nan,np.nan,np.nan,C[:-3]]
# 方向が同じ向きで続いた本数(直前の足まで)
sg=np.sign(mom3); age=np.zeros(N,int)
for i in range(1,N):
    age[i]=age[i-1]+1 if (sg[i-1]==sg[i] and sg[i]!=0) else 0
# age[i] = 今の足と同じ向きが直前に何本続いたか
# M5 RSI(9) 形成中: 各M1足の終値時点
m5=o.C.resample('5min').last().dropna()
def rsi_live():
    out=np.full(N,50.0); a=1/9
    closes=m5.values; idx5=m5.index
    # 確定したM5のRSIの平均上昇・下降(Wilder)
    d=np.diff(closes,prepend=closes[0]); up=np.clip(d,0,None); dn=np.clip(-d,0,None)
    au=pd.Series(up).ewm(alpha=a,adjust=False).mean().values; ad=pd.Series(dn).ewm(alpha=a,adjust=False).mean().values
    pos=np.searchsorted(idx5.values, (tt.floor('5min')).values)  # 形成中のM5のindex
    for i in range(N):
        j=pos[i]
        if j<1 or j>=len(closes): continue
        dd=C[i]-closes[j-1]; u=(1-a)*au[j-1]+a*max(dd,0); w=(1-a)*ad[j-1]+a*max(-dd,0)
        out[i]=100*u/(u+w) if u+w>0 else 50
    return out
R=rsi_live()
def lots_seq():
    l=[0.01]
    for n in range(1,40): l.append(max(0.01,round(l[-1]*(1.5 if n<10 else 1.2),2)))
    return l
LOTS=lots_seq()

def run(rule,hedge_from=2,maxlegs=40,sl=None,X=1.0,Y=0.3,Z=1.0):
    real=0.0; eq_min=0.0; sl_cnt=0; nb=0; hedge_real=0.0; worst=0.0
    baskets={1:None,-1:None}; last_entry={1:-10**9,-1:-10**9}
    hedges=[]  # dict(side,lot,price,peak,basket_side)
    minfloat=0.0; maxlegs_seen=0; daily=[]
    for i in range(4,N):
        t=tt[i]
        # ---- 初弾(足の始値)
        s=int(sg[i])
        if s!=0 and baskets[s] is None and (i-last_entry[s])>=6 and age[i]<=2 and not np.isnan(K[i]):
            k=K[i] if s>0 else 100-K[i]; kd=(K[i]-D[i])*s
            if kd>0 and 40<k<97:
                px=O[i]+(SP if s>0 else 0)  # 買いはask、売りはbid
                baskets[s]=dict(legs=[(px,LOTS[0])],t=i,peak=None,trig=False,low=px,high=px); last_entry[s]=i; nb+=1
        # ---- ナンピン(足の終値で判定)
        for s in (1,-1):
            b=baskets[s]
            if b is None: continue
            lp,ll=b['legs'][-1]; n=len(b['legs'])
            cur=C[i]+(SP if s>0 else 0)
            adverse=(lp-cur)*s
            if n<maxlegs and (i-b['t'])>=7 and adverse>=1.10:
                ok=True
                if n>=2: ok = (R[i]>=35) if s>0 else (R[i]<=65)
                if ok:
                    lot=LOTS[n]; b['legs'].append((cur,lot)); b['t']=i
                    maxlegs_seen=max(maxlegs_seen,n+1)
                    if n>=hedge_from and rule!='none':
                        hp=C[i]+(0 if s>0 else SP)  # 反対売買: 買い束のヘッジは売り(bid)
                        hedges.append(dict(side=-s,lot=lot,price=hp,peak=0.0,bs=s,rsi_arm=False,ext=cur))
        # ---- ヘッジの決済
        keep=[]
        for h in hedges:
            s=h['side']
            cl=C[i]+(0 if s>0 else SP)  # 買いヘッジはbidで決済、売りヘッジはaskで決済
            best=(H[i] if s>0 else L[i]+SP)
            pr=(cl-h['price'])*s; prbest=(best-h['price'])*s
            done=False
            if rule=='trail':
                h['peak']=max(h['peak'],prbest)
                if h['peak']>=X and pr<=h['peak']-Y and pr>0: done=True
            elif rule=='rsi':
                over=(R[i]<35) if s<0 else (R[i]>65)   # 売りヘッジ=下落の行き過ぎ
                if over: h['rsi_arm']=True
                elif h['rsi_arm'] and pr>0: done=True
            elif rule=='rebound':
                ext=(L[i] if s<0 else H[i]); h['ext']=min(h['ext'],ext) if s<0 else max(h['ext'],ext)
                back=(C[i]-h['ext'])*(-s)
                if back>=Z and pr>0: done=True
            if done:
                v=pr*h['lot']*100*YEN; real+=v; hedge_real+=v
            else: keep.append(h)
        hedges=keep
        # ---- 利確(発動ライン+戻り)
        for s in (1,-1):
            b=baskets[s]
            if b is None: continue
            tl=sum(l for _,l in b['legs']); avg=sum(p*l for p,l in b['legs'])/tl
            one=len(b['legs'])==1; trig=0.67 if one else 1.00; ret=0.07 if one else 0.45
            best=((H[i]-avg) if s>0 else (avg-(L[i]+SP)))
            if best>=trig: b['peak']=max(b['peak'] or 0,best)
            if b['peak'] is not None:
                exitp=b['peak']-ret
                worstbar=((L[i]-avg) if s>0 else (avg-(H[i]+SP)))
                if worstbar<=exitp or True:
                    v=exitp*tl*100*YEN; real+=v; baskets[s]=None
                    # 束の利確でその束のヘッジも全決済
                    rest=[]
                    for h in hedges:
                        if h['bs']==s:
                            cl=C[i]+(0 if h['side']>0 else SP); vv=(cl-h['price'])*h['side']*h['lot']*100*YEN; real+=vv; hedge_real+=vv
                        else: rest.append(h)
                    hedges=rest
        # ---- 含み損
        fl=0.0
        for s in (1,-1):
            b=baskets[s]
            if b is None: continue
            for p,l in b['legs']:
                w=((L[i]-p) if s>0 else (p-(H[i]+SP))); fl+=w*l*100*YEN
        for h in hedges:
            w=((L[i]-h['price']) if h['side']>0 else (h['price']-(H[i]+SP))); fl+=w*h['lot']*100*YEN
        minfloat=min(minfloat,fl)
        if sl and fl<=-sl:
            real+= -sl; sl_cnt+=1; baskets={1:None,-1:None}; hedges=[]
    return dict(rule=rule,baskets=nb,pnl=round(real),hedge_pnl=round(hedge_real),max_float=round(minfloat),sl=sl_cnt,maxlegs=maxlegs_seen)
if __name__=='__main__':
    print(tt[0],tt[-1],N)
    rows=[]
    for sl in (None,5000):
        for r,kw in [('none',{}),('trail',dict(X=1.0,Y=0.3)),('trail',dict(X=2.0,Y=0.5)),('rsi',{}),('rebound',dict(Z=1.0)),('rebound',dict(Z=2.0)),('hold',{})]:
            d=run(r,sl=sl,**kw); d['param']=str(kw); d['SL']=sl; rows.append(d); print(d,flush=True)
    pd.DataFrame(rows).to_csv('hedge_result.csv',index=False)

# 追加の条件(解析33の表の後半): 大きい追いかけ幅、最大段数12、初弾からのヘッジ
def more():
    rows=[]
    for sl in (None,5000):
        for r,kw in [('trail',dict(X=5.0,Y=1.5)),('trail',dict(X=10.0,Y=3.0)),('rebound',dict(Z=5.0)),('none',dict(maxlegs=12)),('hold',dict(maxlegs=12)),('hold',dict(hedge_from=1))]:
            d=run(r,sl=sl,**kw); d['param']=str(kw); d['SL']=sl; rows.append(d); print(d,flush=True)
    pd.DataFrame(rows).to_csv('hedge_result2.csv',index=False)
