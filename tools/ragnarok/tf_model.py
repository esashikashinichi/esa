"""Ragnarok 解析36: トレンドフォローで勝率70%以上の手法を探す(GOLDmicro M15 2.2年)。時間決済は使わない。
入口: ブレイクアウト・MA クロス・トレンド中の押し目(RSI・EMA タッチ・RSI2)・MACD・ADX
フィルター: なし / H1 EMA50 の傾き / H4 終値と EMA50 / ADX
出口: 利確・損切り(ATR の倍数)、建値への移動、追いかけ(シャンデリア)、反対シグナル、SMA5 越え(指標の決済)
同じ足で利確と損切りの両方に届いた時は損切りを先とする(不利な側)。スプレッドは価格の 0.0128%(今の 0.55ドル相当)。
"""
import pandas as pd, numpy as np
YEN=1.576  # 0.01ロットで1ドル
SPR=0.000128
def load_m15(path='../data/GOLDmicro15.csv'):
    d=pd.read_csv(path,header=None,names=['D','T','O','H','L','C','V'])
    d['t']=pd.to_datetime(d['D']+' '+d['T'],format='%Y.%m.%d %H:%M')
    return d.drop_duplicates('t').set_index('t').sort_index()[['O','H','L','C']]
def ema(s,n): return s.ewm(span=n,adjust=False).mean()
def rsi(c,n):
    d=c.diff(); u=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); w=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100*u/(u+w)
def atr(o,n=14):
    tr=pd.concat([o.H-o.L,(o.H-o.C.shift()).abs(),(o.L-o.C.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()
def adx(o,n=14):
    up=o.H.diff(); dn=-o.L.diff()
    pdm=np.where((up>dn)&(up>0),up,0.0); ndm=np.where((dn>up)&(dn>0),dn,0.0)
    a=atr(o,n)
    pdi=100*pd.Series(pdm,index=o.index).ewm(alpha=1/n,adjust=False).mean()/a
    ndi=100*pd.Series(ndm,index=o.index).ewm(alpha=1/n,adjust=False).mean()/a
    dx=100*(pdi-ndi).abs()/(pdi+ndi)
    return dx.ewm(alpha=1/n,adjust=False).mean(),pdi,ndi
def htf(o,rule,n):
    """上位足の EMA(n) の傾きと、終値が EMA の上か下か。確定した上位足だけを使う"""
    c=o.C.resample(rule,label='right',closed='right').last().dropna()
    e=ema(c,n)
    slope=np.sign(e-e.shift(1)); pos=np.sign(c-e)
    # 上位足の確定時刻(右端ラベル)以降の M15 足で使う
    return slope.reindex(o.index,method='ffill').fillna(0).values, pos.reindex(o.index,method='ffill').fillna(0).values

class Data:
    def __init__(self,o):
        self.o=o; self.O,self.H,self.L,self.C=[o[k].values for k in 'OHLC']; self.N=len(o); self.t=o.index
        c=o.C
        self.atr=atr(o).values
        self.e9,self.e20,self.e21,self.e50,self.e200=[ema(c,n).values for n in (9,20,21,50,200)]
        self.sma5=c.rolling(5).mean().values
        self.r14=rsi(c,14).values; self.r2=rsi(c,2).values
        a,p,n_=adx(o); self.adx,self.pdi,self.ndi=a.values,p.values,n_.values
        m=ema(c,12)-ema(c,26); sg=ema(m,9); self.macd=(m-sg).values
        self.hh20=o.H.rolling(20).max().shift(1).values; self.ll20=o.L.rolling(20).min().shift(1).values
        self.hh55=o.H.rolling(55).max().shift(1).values; self.ll55=o.L.rolling(55).min().shift(1).values
        self.h1s,self.h1p=htf(o,'1h',50); self.h4s,self.h4p=htf(o,'4h',50)

def signals(d,entry):
    """足 i の終値で出るシグナル(+1 買い / -1 売り / 0)。発注は i+1 の始値"""
    C,H,L=d.C,d.H,d.L; s=np.zeros(d.N,int); P=lambda a:np.r_[np.nan,a[:-1]]
    if entry.startswith('don'):
        n=int(entry[3:]); hh=d.o.H.rolling(n).max().shift(1).values; ll=d.o.L.rolling(n).min().shift(1).values
        s[C>hh]=1; s[C<ll]=-1
    elif entry=='x9_21':
        u=(d.e9>d.e21)&(P(d.e9)<=P(d.e21)); w=(d.e9<d.e21)&(P(d.e9)>=P(d.e21)); s[u]=1; s[w]=-1
    elif entry=='x20_50':
        u=(d.e20>d.e50)&(P(d.e20)<=P(d.e50)); w=(d.e20<d.e50)&(P(d.e20)>=P(d.e50)); s[u]=1; s[w]=-1
    elif entry=='pb_rsi':   # 上昇(EMA50>EMA200)中、RSI14 が40を下から上に戻した
        up=d.e50>d.e200; dn=d.e50<d.e200
        s[up&(d.r14>40)&(P(d.r14)<=40)]=1; s[dn&(d.r14<60)&(P(d.r14)>=60)]=-1
    elif entry=='pb_ema':   # EMA20>EMA50>EMA200 の並びで、安値が EMA20 に触れて陽線で EMA20 の上に引けた
        up=(d.e20>d.e50)&(d.e50>d.e200); dn=(d.e20<d.e50)&(d.e50<d.e200)
        s[up&(L<=d.e20)&(C>d.e20)&(C>d.O)]=1; s[dn&(H>=d.e20)&(C<d.e20)&(C<d.O)]=-1
    elif entry=='rsi2':     # 終値が EMA200 の上で RSI2 が10未満(押し目)
        s[(C>d.e200)&(d.r2<10)]=1; s[(C<d.e200)&(d.r2>90)]=-1
    elif entry=='macd':
        u=(d.macd>0)&(P(d.macd)<=0); w=(d.macd<0)&(P(d.macd)>=0); s[u]=1; s[w]=-1
    elif entry=='adx':      # ADX>25 で +DI>-DI、終値が EMA20 を上抜け
        u=(d.adx>25)&(d.pdi>d.ndi)&(C>d.e20)&(P(C)<=P(d.e20)); w=(d.adx>25)&(d.ndi>d.pdi)&(C<d.e20)&(P(C)>=P(d.e20)); s[u]=1; s[w]=-1
    return s

def apply_filter(d,s,f):
    s=s.copy()
    if f=='h1': s[(s==1)&(d.h1s<=0)]=0; s[(s==-1)&(d.h1s>=0)]=0
    elif f=='h4': s[(s==1)&(d.h4p<=0)]=0; s[(s==-1)&(d.h4p>=0)]=0
    elif f=='h1h4': s[(s==1)&((d.h1s<=0)|(d.h4p<=0))]=0; s[(s==-1)&((d.h1s>=0)|(d.h4p>=0))]=0
    elif f=='adx20': s[d.adx<20]=0
    elif f=='h4adx': s[(s==1)&(d.h4p<=0)]=0; s[(s==-1)&(d.h4p>=0)]=0; s[d.adx<20]=0
    return s

def simulate(d,s,exit,tp=1.0,sl=1.0,be=None,trail=None,i0=0,i1=None,res=None,frac=0.5):
    """1建玉ずつ。exit: 'fix'(利確 tp×ATR・損切り sl×ATR、be が有れば be×ATR 含み益で損切りを建値+スプレッドへ)
       'trail'(損切り sl×ATR、最高値から trail×ATR で追いかけ)/ 'opp'(反対シグナルで決済、損切り sl×ATR)/ 'sma5'(終値が SMA5 を越えたら決済、損切り sl×ATR)
       res: M1 で足の中の順番を解く関数(任意)。戻り値は1取引ごとの (入口足, 出口足, 方向, 損益ドル)"""
    O,H,L,C=d.O,d.H,d.L,d.C; i1=i1 or d.N; out=[]; i=max(i0,200)
    while i<i1-1:
        k=s[i]
        if k==0 or np.isnan(d.atr[i]): i+=1; continue
        e=O[i+1]; sp=e*SPR; a=d.atr[i]
        px=e+sp if k>0 else e   # 買いは ask、売りは bid。決済は反対側
        SL=px-k*sl*a; TP=px+k*tp*a if exit in ('fix','part') else None; moved=False; best=px; booked=0.0; rem=1.0
        j=i+1; ex=None; kind=None
        while j<i1:
            hi=H[j]+(sp if k<0 else 0); lo=L[j]+(sp if k<0 else 0)  # 売りの決済は ask
            fav=hi if k>0 else lo; adv=lo if k>0 else hi
            op=O[j]+(sp if k<0 else 0)
            if res is not None:
                r=res(j,k,SL,TP)
                if r is not None: ex,kind=r,('sl' if (r-SL)*k<=1e-9 else 'tp'); break
            else:
                if (op-SL)*k<=0: ex=op; kind='sl'; break          # 窓開けで損切りより先から始まった足は始値で決済
                if TP is not None and (op-TP)*k>=0: ex=op; kind='tp'; break
                if (adv-SL)*k<=0: ex=SL; kind='sl'; break
                if exit=='part' and TP is not None and (fav-TP)*k>=0:
                    booked=frac*(TP-px)*k; rem=1-frac; TP=None; SL=px+k*sp; moved=True; best=fav
                    if (cl_:=C[j]+(sp if k<0 else 0)-SL)*k<=0: ex=SL; kind='be'; break
                    j+=1; continue
                if TP is not None and (fav-TP)*k>=0: ex=TP; kind='tp'; break
            cl=C[j]+(sp if k<0 else 0)
            if exit=='fix' and be and not moved and (fav-px)*k>=be*a:
                SL=px+k*sp; moved=True
                # この足で含み益が be×ATR に届いた後、終値が建値より下で引けた → 足の中で建値の損切りに当たっている(高値の後に終値が来るため順番が決まる)
                if (cl-SL)*k<=0: ex=SL; kind='be'; break
            if exit=='trail' or (exit=='part' and moved):
                best=max(best,fav) if k>0 else min(best,fav); ns=best-k*trail*a
                if (ns-SL)*k>0:
                    SL=ns
                    if (cl-SL)*k<=0: ex=SL; kind='sl'; break   # 同じ理由で、この足の中で追いかけの損切りに当たっている
            if exit=='opp' and s[j]==-k: ex=cl; kind='sig'; break
            if exit=='sma5' and ((k>0 and C[j]>d.sma5[j]) or (k<0 and C[j]<d.sma5[j])): ex=cl; kind='sig'; break
            j+=1
        if ex is None: ex=C[i1-1]+(sp if k<0 else 0); j=i1-1; kind='end'
        if kind=='sl' and moved: kind='be'   # 建値に動かした損切りで決済
        if exit=='part' and moved: kind='part'  # 部分利確の後、残りを決済
        out.append((i,j,k,booked+rem*(ex-px)*k,kind))
        i=j+1
    return out

def stats(tr,d=None):
    if not tr: return dict(n=0,win=0,pf=0,exp=0,total=0,dd=0)
    p=np.array([x[3] for x in tr]); w=p[p>0]; l=p[p<=0]
    kinds=[x[4] for x in tr]; be_w=sum(1 for x in tr if x[4]=='be' and x[3]>0)
    cum=np.cumsum(p*YEN); dd=(cum-np.maximum.accumulate(np.r_[0,cum][1:])).min()
    return dict(n=len(p),win=round(100*len(w)/len(p),1),avgw=round(w.mean(),2) if len(w) else 0,avgl=round(l.mean(),2) if len(l) else 0,
                pf=round(w.sum()/-l.sum(),2) if l.sum()<0 else 99,exp=round(p.mean()*YEN,2),total=round(p.sum()*YEN),dd=round(dd),
                bewin=round(100*be_w/len(p),1),tpwin=round(100*(len(w)-be_w)/len(p),1))
