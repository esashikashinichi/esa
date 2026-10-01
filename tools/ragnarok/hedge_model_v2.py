"""Ragnarok 解析34: b 型 + ヘッジ・段数上限・時間の上限などのバックテスト(M1 足)。解析33のモデルのロットの丸めを直し、期間末の含み損を損益に入れた版"""

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
def lots_seq(lot0=0.01,mult=1.5):
    # ラグナロクと同じく、丸める前の値に掛け続けて、各段で0.01単位に四捨五入する
    # (デモの実測: 0.01,0.02,0.02,0.03,0.05,0.08,0.11,0.17,0.26,0.38,0.46,0.55,0.66,0.80,0.96)
    out=[]; raw=lot0
    for n in range(40):
        if n>0: raw*= (mult if n<10 else min(mult,1.2))
        out.append(max(0.01,float(int(raw*100+0.5+1e-9))/100))
    return out
LOTS=lots_seq()
# 上位足のトレンド(直前に確定した足までで計算): H1 の MA20 の傾き、M15 の終値と MA50
_h1=o.C.resample('1h').last().dropna(); _h1ma=_h1.rolling(20).mean()
H1SLOPE=np.sign((_h1ma-_h1ma.shift(3)).shift(1).reindex(tt,method='ffill').fillna(0).values)
_m15=o.C.resample('15min').last().dropna(); _m15ma=_m15.rolling(50).mean()
M15POS=np.sign((_m15-_m15ma).shift(1).reindex(tt,method='ffill').fillna(0).values)
# 日足の始値(サーバー0時)からの値動き
_dopen=o.O.resample('1D').first(); DOPEN=_dopen.reindex(tt.floor('1D')).values


def run(rule,hedge_from=2,maxlegs=40,sl=None,X=1.0,Y=0.3,Z=1.0,step=1.10,mult=1.5,kdmin=0.0,tps=1.0,bsl=None,i0=4,i1=None,lot0=0.01,wait=7,unlock=None,tf=None,dmax=None,tstop=None):
    LT=lots_seq(lot0,mult)
    real=0.0; eq_min=0.0; sl_cnt=0; nb=0; hedge_real=0.0; worst=0.0
    baskets={1:None,-1:None}; last_entry={1:-10**9,-1:-10**9}
    hedges=[]  # dict(side,lot,price,peak,basket_side)
    minfloat=0.0; maxlegs_seen=0; daily=[]
    i1=i1 or N
    for i in range(i0,i1):
        t=tt[i]
        # ---- 初弾(足の始値)
        s=int(sg[i])
        if s!=0 and baskets[s] is None and (i-last_entry[s])>=6 and age[i]<=2 and not np.isnan(K[i]):
            k=K[i] if s>0 else 100-K[i]; kd=(K[i]-D[i])*s
            okf=True
            if tf=='h1' and H1SLOPE[i]==-s: okf=False
            if tf=='m15' and M15POS[i]==-s: okf=False
            if dmax is not None and (O[i]-DOPEN[i])*(-s)>dmax: okf=False  # 日足始値から逆方向にdmaxドル以上動いた日は逆張り方向の新規を止める
            if okf and kd>kdmin and 40<k<97:
                px=O[i]+(SP if s>0 else 0)  # 買いはask、売りはbid
                baskets[s]=dict(legs=[(px,LT[0])],t0=i,t=i,peak=None,trig=False,low=px,high=px); last_entry[s]=i; nb+=1
        # ---- ナンピン(足の終値で判定)
        for s in (1,-1):
            b=baskets[s]
            if b is None: continue
            lp,ll=b['legs'][-1]; n=len(b['legs'])
            cur=C[i]+(SP if s>0 else 0)
            adverse=(lp-cur)*s
            if n<maxlegs and (i-b['t'])>=wait and adverse>=step:
                ok=True
                if n>=2: ok = (R[i]>=35) if s>0 else (R[i]<=65)
                if ok:
                    lot=LT[n]; b['legs'].append((cur,lot)); b['t']=i
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
            one=len(b['legs'])==1; trig=(0.67 if one else 1.00)*tps; ret=0.07 if one else 0.45
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
        # ---- 束ごとの損切り
        if bsl:
            for s_ in (1,-1):
                b=baskets[s_]
                if b is None: continue
                v=sum(((C[i]-p) if s_>0 else (p-(C[i]+SP)))*l for p,l in b['legs'])*100*YEN
                hv=sum(((C[i]+(0 if h['side']>0 else SP))-h['price'])*h['side']*h['lot'] for h in hedges if h['bs']==s_)*100*YEN
                if v+hv<=-bsl:
                    real+=v+hv; baskets[s_]=None; hedges=[h for h in hedges if h['bs']!=s_]; sl_cnt+=1
        # ---- 時間の上限: 束を tstop 時間より長く持ったら、ヘッジごと決済
        if tstop:
            for s_ in (1,-1):
                b=baskets[s_]
                if b is None or (i-b['t0'])<tstop*60: continue
                v=sum(((C[i]-p) if s_>0 else (p-(C[i]+SP)))*l for p,l in b['legs'])*100*YEN
                hv=sum(((C[i]+(0 if h['side']>0 else SP))-h['price'])*h['side']*h['lot'] for h in hedges if h['bs']==s_)*100*YEN
                real+=v+hv; hedge_real+=hv; baskets[s_]=None; hedges=[h for h in hedges if h['bs']!=s_]
        # ---- ロックの解除: 束の逆行の端から unlock ドル戻ったら、プラスのヘッジだけ外す
        if unlock and rule=='hold':
            keep=[]
            for h in hedges:
                ext=(L[i] if h['side']<0 else H[i]); h['ext']=min(h['ext'],ext) if h['side']<0 else max(h['ext'],ext)
                back=(C[i]-h['ext'])*(-h['side']); cl=C[i]+(0 if h['side']>0 else SP); pr=(cl-h['price'])*h['side']
                if back>=unlock and pr>0: real+=pr*h['lot']*100*YEN; hedge_real+=pr*h['lot']*100*YEN
                else: keep.append(h)
            hedges=keep
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
    j=i1-1  # 期間の終わりに残った建玉は、最後の終値で決済したものとして損益に入れる
    open_mtm=0.0
    for s_ in (1,-1):
        b=baskets[s_]
        if b is None: continue
        open_mtm+=sum(((C[j]-p) if s_>0 else (p-(C[j]+SP)))*l for p,l in b['legs'])*100*YEN
    for hh in hedges:
        open_mtm+=((C[j]+(0 if hh['side']>0 else SP))-hh['price'])*hh['side']*hh['lot']*100*YEN
    real+=open_mtm
    return dict(rule=rule,open_mtm=round(open_mtm),baskets=nb,pnl=round(real),hedge_pnl=round(hedge_real),max_float=round(minfloat),sl=sl_cnt,maxlegs=maxlegs_seen)
if __name__=='__main__':
    print(tt[0],tt[-1],N)
    rows=[]
    for sl in (None,5000):
        for r,kw in [('none',{}),('trail',dict(X=1.0,Y=0.3)),('trail',dict(X=2.0,Y=0.5)),('rsi',{}),('rebound',dict(Z=1.0)),('rebound',dict(Z=2.0)),('hold',{})]:
            d=run(r,sl=sl,**kw); d['param']=str(kw); d['SL']=sl; rows.append(d); print(d,flush=True)
    pd.DataFrame(rows).to_csv('hedge_result.csv',index=False)
