"""解析56: 組み合わせ(複数方式を1つの EA で同時に動かす)で、1万円→3万円まで最短になる組を探す。
段階1(学習): M15 の 2024-08〜2026-04-12 を、始点6通り(2024-08/11、2025-02/05/08/11)で、候補19個から 1〜4個の全組み合わせ(5,035通り)× 合計の複利の強さ Kc 12段階。
  Kc は各候補が m=floor((1万円+確定損益)/Kc) 倍(最小1・最大30)で動く値。制約: 落ち込み最大 45%(通常)・55%(スプレッド2倍)。その中で最も小さい Kc(最強の複利)を選び、3倍までの日数の中央値で並べる。
段階2(未使用期間での検証): 2026-04-13〜09-21 を M5 足の約定で(同じ Kc で)動かす。選ぶ時に一切見ていない期間。
近似: 候補ごとに 1 単位(0.01 ロット)で走らせたバーごとの損益を足し、共通の複利倍率を掛ける(R 1個で正確なエンジンとの誤差は 1% 以内)。"""
import numpy as np, pandas as pd, itertools, sys
from numba import njit
import tf_model as t, tf_sl4 as sl, tf_rank as r, tf_rank_m5 as q
d=r.d; M=q.M; E0=r.E0; YEN=t.YEN; idx=d.o.index; N=d.N
names=list(r.C.keys()); NC=len(names)
iM=M.i0   # M5 開始に対応する M15 の足
STARTS=[int(np.searchsorted(idx.values,np.datetime64(x+'-01'))) for x in ('2024-08','2024-11','2025-02','2025-05','2025-08','2025-11')]
KCS=np.array([500,750,1000,1500,2000,3000,4000,5000,7500,10000,15000,20000],float)
def stream(name,tf,spr,i0,i1=None):
    s,c,sl0=r.C[name]
    if tf=='M15': x=sl.engine(d.O,d.H,d.L,d.C,r.ev(name),r.cf(c),i0=i0,i1=i1,spr=spr); lo,hi=i0,(i1 or N)
    else: x=sl.engine(M.O,M.H,M.L,M.C,q.ev5(name),r.cf(c),i0=1,spr=spr); lo,hi=1,len(M.O)
    n=len(x['eqc']); rz=np.zeros(n)
    for tr in x['trades']: rz[tr[1]]+=tr[0]
    ec=x['eqc'][lo:hi]; ea=x['eqa'][lo:hi]; z=rz[lo:hi]
    de=np.diff(ec,prepend=0.0); da=ea-np.r_[0.0,ec[:-1]]
    return de.astype(np.float64),da.astype(np.float64),z.astype(np.float64)
@njit(cache=True)
def sim(de,da,rz,Kc,tday,E0,YEN,mmax):
    E=E0; Rr=0.0; peak=E0; mdd=0.0; first=-1.0
    for j in range(len(de)):
        m=int((E0+Rr)//Kc)
        if m<1: m=1
        if m>mmax: m=mmax
        adv=E+m*da[j]*YEN
        if E>peak: peak=E
        dd=(peak-adv)/peak
        if dd>mdd: mdd=dd
        E+=m*de[j]*YEN; Rr+=m*rz[j]*YEN
        if first<0 and E>=3*E0: first=tday[j]
        if E<=0: E=0.0; break
    return E,mdd*100,first
def build():
    import os
    P={}   # (cand,start_idx or 'T',spr)->(de,da,rz)
    for ci,n in enumerate(names):
        for sp,spr in ((0,None),(1,t.SPR*2)):
            for si,i0 in enumerate(STARTS): P[(ci,si,sp)]=stream(n,'M15',spr,i0,iM)
            P[(ci,'M5',sp)]=stream(n,'M5',spr,1)
            P[(ci,'T15',sp)]=stream(n,'M15',spr,iM)
        print(n,flush=True)
    return P
def tdays(i0,n,tf): 
    ix=idx.values[i0:i0+n] if tf=='M15' else M.m.index.values[1:1+n]
    return ((ix-ix[0]).astype('timedelta64[h]').astype(float)/24.0)
if __name__=='__main__':
    P=build(); mmax=30
    TD=[tdays(i0,len(P[(0,si,0)][0]),'M15') for si,i0 in enumerate(STARTS)]
    rows=[]
    subs=[c for k in (1,2,3,4) for c in itertools.combinations(range(NC),k)]
    print(len(subs),'組み合わせ',flush=True)
    for si_,sub in enumerate(subs):
        S={}
        for sp in (0,1):
            for si in range(len(STARTS)):
                S[(si,sp)]=tuple(sum(P[(c,si,sp)][k] for c in sub) for k in range(3))
        best=None
        for Kc in KCS:   # 小さい Kc(強い複利)から
            ok=True; res=[]
            for sp,lim in ((0,45),(1,55)):
                dds=[];fin=[];d3=[]
                for si in range(len(STARTS)):
                    de,da,rz=S[(si,sp)]; f,dd,fr=sim(de,da,rz,Kc,TD[si],E0,YEN,mmax); dds.append(dd);fin.append(f);d3.append(fr if fr>=0 else np.inf)
                if max(dds)>lim: ok=False; break
                res.append((max(dds),float(np.median(d3)),sum(np.isfinite(d3)),min(fin),float(np.median(fin))))
            if ok: best=(Kc,res); break
        if best is None: continue
        Kc,(r0,r1)=best
        rows.append(dict(sub=sub,n=len(sub),Kc=Kc,dd=r0[0],d3=r0[1],reach=r0[2],fmin=r0[3],fmed=r0[4],dd2=r1[0],d3_2=r1[1],reach2=r1[2],fmin2=r1[3],fmed2=r1[4]))
    X=pd.DataFrame(rows); X['key']=X['sub'].apply(lambda s:'|'.join(names[c] for c in s)); X.to_pickle('tf_combo_train.pkl')
    # 段階2: 未使用期間(上位 60 を d3→d3_2 の順で)
    top=X[(X.reach>=4)].sort_values(['d3','d3_2']).head(60)
    out=[]
    for _,w in top.iterrows():
        sub=w['sub']; Kc=w.Kc; o=dict(key=w.key,Kc=Kc,n=w.n,d3=w.d3,reach=w.reach,dd=w.dd,d3_2=w.d3_2,dd2=w.dd2)
        for tf in ('M5','T15'):
            for sp,lab in ((0,'n'),(1,'s')):
                de,da,rz=[sum(P[(c,tf,sp)][k] for c in sub) for k in range(3)]
                td=tdays(1 if tf=='M5' else iM,len(de),'M5' if tf=='M5' else 'M15')
                f,dd,fr=sim(de,da,rz,Kc,td,E0,YEN,mmax); o[f'{tf}_{lab}_final']=round(f); o[f'{tf}_{lab}_dd']=round(dd,1)
        out.append(o)
    pd.DataFrame(out).to_pickle('tf_combo_test.pkl'); print('done',len(X),len(out))
