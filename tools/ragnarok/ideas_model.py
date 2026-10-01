"""Ragnarok 解析35: ナンピン EA で勝つための案(A1〜B5・C2)の検証モデル(M1 足)。
hedge_model_v2.py(解析34)の run() に、次の案を足した版。ヘッジは使わない。
  A1 vr      : 分散比(VR)が大きい(トレンド)間はナンピンしない / 新規も止める
  A2 hl      : 戻りの半減期(OU)から、束を持つ時間の上限を決める
  A3 atr     : M15 ATR が下がっている時だけ新規
  A4 asym    : 売りの束を制限(売りはナンピン無し / 売りは新規しない)
  A5 nh      : 指定の時間帯(サーバー時間)はナンピンしない
  A6 roll    : ロールオーバー(サーバー0時)の前後はナンピン・新規しない
  B1 flip    : 時間の上限・束の損切りで切った時、トレンドの向きに入る
  B3 trig    : 束が trig 段に達したら、トレンドの向きに入る(束は持ったまま)
  B4 pair    : 一番古い段と一番新しい段の合計がプラスになったら、2つだけ決済
  B5 grow    : ナンピン幅を段ごとに広げる(step × grow^(n-1))
  B2         : 別関数 donchian()(M15 のブレイクアウト)
  C2         : 別関数 equity_sim()(出金・ゼロカット)
"""
import pandas as pd, numpy as np
SP=0.55; YEN=1.576
def load():
    a=pd.read_csv('../data/M1_long.csv',header=None,names=['D','T','O','H','L','C','V'])
    b=pd.read_csv('../d38/m1ohlc.csv'); b.columns=['D','T','O','H','L','C','V']
    d=pd.concat([a,b]); d['t']=pd.to_datetime(d['D']+' '+d['T'],format='%Y.%m.%d %H:%M')
    return d.drop_duplicates('t').set_index('t').sort_index()
o=load()
O,H,L,C=o.O.values,o.H.values,o.L.values,o.C.values; N=len(o); tt=o.index
HOUR=tt.hour.values; MIN=tt.minute.values
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
sg=np.sign(mom3); age=np.zeros(N,int)
for i in range(1,N):
    age[i]=age[i-1]+1 if (sg[i-1]==sg[i] and sg[i]!=0) else 0
m5=o.C.resample('5min').last().dropna()
def rsi_live():
    out=np.full(N,50.0); a=1/9
    closes=m5.values; idx5=m5.index
    d=np.diff(closes,prepend=closes[0]); up=np.clip(d,0,None); dn=np.clip(-d,0,None)
    au=pd.Series(up).ewm(alpha=a,adjust=False).mean().values; ad=pd.Series(dn).ewm(alpha=a,adjust=False).mean().values
    pos=np.searchsorted(idx5.values,(tt.floor('5min')).values)
    for i in range(N):
        j=pos[i]
        if j<1 or j>=len(closes): continue
        dd=C[i]-closes[j-1]; u=(1-a)*au[j-1]+a*max(dd,0); w=(1-a)*ad[j-1]+a*max(-dd,0)
        out[i]=100*u/(u+w) if u+w>0 else 50
    return out
R=rsi_live()
def lots_seq(lot0=0.01,mult=1.5):
    out=[]; raw=lot0
    for n in range(40):
        if n>0: raw*=(mult if n<10 else min(mult,1.2))
        out.append(max(0.01,float(int(raw*100+0.5+1e-9))/100))
    return out
_dopen=o.O.resample('1D').first(); DOPEN=_dopen.reindex(tt.floor('1D')).values

# ---- A1 分散比: 直前に確定した足まで。VR = var(q本の値動き) / (q × var(1本の値動き))。1未満=戻る、1超=トレンド
def vr(q,W):
    c=o.C; r1=c.diff(); rq=c-c.shift(q)
    v=(rq.rolling(W).var()/(q*r1.rolling(W).var())).shift(1)
    return v.fillna(1.0).values
VR={}
def get_vr(q,W):
    if (q,W) not in VR: VR[(q,W)]=vr(q,W)
    return VR[(q,W)]
# ---- A2 戻りの半減期(分): M5 終値の AR(1)。dp = a + b*p_lag、半減期 = -ln2/ln(1+b)。b>=0 は戻らない(無限大)
def halflife(W5):
    p=m5; dp=p.diff(); pl=p.shift(1)
    cov=(dp*pl).rolling(W5).mean()-dp.rolling(W5).mean()*pl.rolling(W5).mean()
    var=pl.rolling(W5).var(ddof=0); b=cov/var
    hl=(-np.log(2)/np.log1p(b.clip(upper=-1e-9)))*5  # 分
    hl[b>=0]=np.inf
    hl=hl.shift(1)  # 確定した M5 まで
    return hl.reindex(tt,method='ffill').fillna(np.inf).values
HL={}
def get_hl(W5):
    if W5 not in HL: HL[W5]=halflife(W5)
    return HL[W5]
# ---- A3 M15 ATR(14)、直前に確定した足まで
_m15=o.resample('15min').agg({'H':'max','L':'min','C':'last'}).dropna()
_tr=pd.concat([_m15.H-_m15.L,(_m15.H-_m15.C.shift(1)).abs(),(_m15.L-_m15.C.shift(1)).abs()],axis=1).max(axis=1)
_atr=_tr.ewm(alpha=1/14,adjust=False).mean()
ATR_FALL=((_atr<_atr.shift(4)).shift(1)).reindex(tt,method='ffill').fillna(False).values
ATR_HIGH=((_atr>_atr.rolling(96*5).median()).shift(1)).reindex(tt,method='ffill').fillna(False).values

def run(maxlegs=3,step=4.0,mult=1.5,tstop=6,dmax=20,sl=5000,bsl=None,tps=1.0,kdmin=0.0,i0=4,i1=None,lot0=0.01,wait=7,
        vr_q=None,vr_W=240,vr_thr=1.0,vr_mode='nanpin',
        hl_k=None,hl_W5=576,hl_min=1.0,hl_max=24.0,
        atr=None, asym=None, nh=None, roll=False,
        flip=None,flip_lot=1.0,flip_trail=3.0,flip_init=3.0,flip_hours=24,trig=None,
        pair=None, grow=1.0, log=False):
    LT=lots_seq(lot0,mult); i1=i1 or N
    vrv=get_vr(vr_q,vr_W) if vr_q else None
    hlv=get_hl(hl_W5) if hl_k else None
    real=0.0; sl_cnt=0; nb=0; minfloat=0.0; maxlegs_seen=0
    side_pnl={1:0.0,-1:0.0}; trend_pnl=0.0; n_trend=0; n_pair=0; n_tstop=0
    baskets={1:None,-1:None}; last_entry={1:-10**9,-1:-10**9}
    trends=[]
    REAL=np.zeros(i1-i0) if log else None; FL=np.zeros(i1-i0) if log else None
    def bval(b,s_,px):  # 束の評価額(円)
        return sum(((px-p) if s_>0 else (p-(px+SP)))*l for p,l in b['legs'])*100*YEN
    def open_trend(s_,lot,i):
        nonlocal n_trend
        px=C[i]+(SP if s_>0 else 0)
        trends.append(dict(side=s_,lot=round(max(0.01,lot),2),p=px,best=0.0,t0=i)); n_trend+=1
    for i in range(i0,i1):
        rollblock = roll and ((HOUR[i]==23 and MIN[i]>=45) or (HOUR[i]==0 and MIN[i]<15))
        # ---- 初弾
        s=int(sg[i])
        if s!=0 and baskets[s] is None and (i-last_entry[s])>=6 and age[i]<=2 and not np.isnan(K[i]):
            k=K[i] if s>0 else 100-K[i]; kd=(K[i]-D[i])*s
            ok=kd>kdmin and 40<k<97
            if dmax is not None and (O[i]-DOPEN[i])*(-s)>dmax: ok=False
            if vrv is not None and vr_mode=='both' and vrv[i]>vr_thr: ok=False
            if atr=='fall' and not ATR_FALL[i]: ok=False
            if atr=='highfall' and not (ATR_FALL[i] and ATR_HIGH[i]): ok=False
            if asym=='buyonly' and s<0: ok=False
            if rollblock: ok=False
            if ok:
                px=O[i]+(SP if s>0 else 0)
                baskets[s]=dict(legs=[(px,LT[0])],k=1,lp=px,t0=i,t=i,peak=None,trig_done=False); last_entry[s]=i; nb+=1
        # ---- ナンピン
        for s in (1,-1):
            b=baskets[s]
            if b is None: continue
            n=len(b['legs']); cur=C[i]+(SP if s>0 else 0)
            ml=maxlegs
            if asym=='sellnonanpin' and s<0: ml=1
            st=step*(grow**(b['k']-1))
            if n<ml and (i-b['t'])>=wait and (b['lp']-cur)*s>=st:
                ok=True
                if b['k']>=2: ok=(R[i]>=35) if s>0 else (R[i]<=65)
                if vrv is not None and vrv[i]>vr_thr: ok=False
                if nh is not None and nh[0]<=HOUR[i]<nh[1]: ok=False
                if rollblock: ok=False
                if ok:
                    lot=LT[min(b['k'],39)]; b['legs'].append((cur,lot)); b['k']+=1; b['lp']=cur; b['t']=i
                    maxlegs_seen=max(maxlegs_seen,len(b['legs']))
                    if trig and len(b['legs'])>=trig and not b['trig_done']:
                        b['trig_done']=True; open_trend(-s,flip_lot*sum(l for _,l in b['legs']),i)
        # ---- B4 ペア決済
        if pair is not None:
            for s in (1,-1):
                b=baskets[s]
                if b is None or len(b['legs'])<3: continue
                (p0,l0),(pn_,ln_)=b['legs'][0],b['legs'][-1]
                v=(((C[i]-p0)*l0+(C[i]-pn_)*ln_) if s>0 else ((p0-(C[i]+SP))*l0+(pn_-(C[i]+SP))*ln_))*100*YEN
                if v>=pair:
                    real+=v; side_pnl[s]+=v; b['legs']=b['legs'][1:-1]; n_pair+=1
        # ---- 利確
        for s in (1,-1):
            b=baskets[s]
            if b is None: continue
            tl=sum(l for _,l in b['legs']); avg=sum(p*l for p,l in b['legs'])/tl
            one=len(b['legs'])==1; trg=(0.67 if one else 1.00)*tps; ret=0.07 if one else 0.45
            best=((H[i]-avg) if s>0 else (avg-(L[i]+SP)))
            if best>=trg: b['peak']=max(b['peak'] or 0,best)
            if b['peak'] is not None:
                v=(b['peak']-ret)*tl*100*YEN; real+=v; side_pnl[s]+=v; baskets[s]=None
        # ---- 束の損切り・時間の上限
        for s in (1,-1):
            b=baskets[s]
            if b is None: continue
            v=bval(b,s,C[i]); cut=False
            if bsl and v<=-bsl: cut=True; sl_cnt+=1
            lim=tstop
            if hlv is not None:
                h=hlv[b['t0']]
                lim=hl_max if not np.isfinite(h) else min(hl_max,max(hl_min,hl_k*h/60))
            if lim and (i-b['t0'])>=lim*60: cut=True; n_tstop+=1
            if cut:
                real+=v; side_pnl[s]+=v; baskets[s]=None
                if flip: open_trend(-s,flip_lot*sum(l for _,l in b['legs']),i)
        # ---- トレンド側の建玉(B1・B3): 初期の損切り、追いかけの損切り、時間の上限
        keep=[]
        for tr in trends:
            s_=tr['side']
            fav=((H[i]-tr['p']) if s_>0 else (tr['p']-(L[i]+SP)))
            tr['best']=max(tr['best'],fav)
            adv=((L[i]-tr['p']) if s_>0 else (tr['p']-(H[i]+SP)))
            ex=None
            if adv<=-flip_init and tr['best']<flip_trail: ex=-flip_init
            elif tr['best']>=flip_trail and (((C[i]-tr['p']) if s_>0 else (tr['p']-(C[i]+SP))) <= tr['best']-flip_trail): ex=tr['best']-flip_trail
            elif (i-tr['t0'])>=flip_hours*60: ex=((C[i]-tr['p']) if s_>0 else (tr['p']-(C[i]+SP)))
            if ex is not None:
                v=ex*tr['lot']*100*YEN; real+=v; trend_pnl+=v
            else: keep.append(tr)
        trends=keep
        # ---- 含み損と口座の損切り
        fl=0.0
        for s in (1,-1):
            b=baskets[s]
            if b is None: continue
            for p,l in b['legs']: fl+=((L[i]-p) if s>0 else (p-(H[i]+SP)))*l*100*YEN
        for tr in trends:
            fl+=((L[i]-tr['p']) if tr['side']>0 else (tr['p']-(H[i]+SP)))*tr['lot']*100*YEN
        minfloat=min(minfloat,fl)
        if sl and fl<=-sl:
            real+=-sl; sl_cnt+=1; baskets={1:None,-1:None}; trends=[]; fl=0.0
        if log: REAL[i-i0]=real; FL[i-i0]=fl
    j=i1-1; mtm=0.0
    for s in (1,-1):
        if baskets[s] is not None: mtm+=bval(baskets[s],s,C[j])
    for tr in trends: mtm+=((C[j]-tr['p']) if tr['side']>0 else (tr['p']-(C[j]+SP)))*tr['lot']*100*YEN
    real+=mtm
    out=dict(pnl=round(real),max_float=round(minfloat),sl=sl_cnt,baskets=nb,buy=round(side_pnl[1]),sell=round(side_pnl[-1]),
             trend=round(trend_pnl),n_trend=n_trend,n_pair=n_pair,n_tstop=n_tstop,maxlegs=maxlegs_seen)
    if log: out['REAL']=REAL; out['FL']=FL
    return out

# ---- B2 M15 ドンチャン・ブレイクアウト(直前 n_in 本の高値・安値を抜けたら入る、n_out 本の逆側を抜けたら決済。常にどちらかを持つ形ではない)
def donchian(n_in=20,n_out=10,lot=0.01,i0=4,i1=None):
    i1=i1 or N
    m=o.iloc[i0:i1].resample('15min').agg({'O':'first','H':'max','L':'min','C':'last'}).dropna()
    hi=m.H.rolling(n_in).max().shift(1).values; lo=m.L.rolling(n_in).min().shift(1).values
    ho=m.H.rolling(n_out).max().shift(1).values; lo_=m.L.rolling(n_out).min().shift(1).values
    pos=0; p=0.0; pnl=0.0; daily={}; n=0; mf=0.0
    for j in range(len(m)):
        d=m.index[j].normalize()
        if pos==1 and m.L.values[j]<=lo_[j]:
            v=(min(lo_[j],m.O.values[j])-p)*lot*100*YEN; pnl+=v; daily[d]=daily.get(d,0)+v; pos=0
        elif pos==-1 and m.H.values[j]>=ho[j]:
            v=(p-(max(ho[j],m.O.values[j])+SP))*lot*100*YEN; pnl+=v; daily[d]=daily.get(d,0)+v; pos=0
        if pos==0 and not np.isnan(hi[j]):
            if m.H.values[j]>=hi[j]: pos=1; p=max(hi[j],m.O.values[j])+SP; n+=1
            elif m.L.values[j]<=lo[j]: pos=-1; p=min(lo[j],m.O.values[j]); n+=1
        if pos!=0:
            w=((m.L.values[j]-p) if pos>0 else (p-(m.H.values[j]+SP)))*lot*100*YEN; mf=min(mf,w)
    return dict(pnl=round(pnl),n=n,max_float=round(mf)),pd.Series(daily)
