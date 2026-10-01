"""解析43 第2段: 上位の組み合わせの頑健さ(始点を毎月ずらす・M5・取引順の入れ替え)"""
import numpy as np, pandas as pd, tf_model as t, tf_sl4 as sl, tf_pyr as p, tf_comp as c, tf_m5 as m5, tf_fast as f
from multiprocessing import Pool
d=f.d; idx=f.idx; E0=f.E0; YEN=t.YEN
CANDS=[('R+rc14','×1.5 利確0.3',750),('R+rc14','×1.5 利確0.3',1000),('R+rc14','×1.5 利確0.3',1500),('R+rc2','×1.5 利確0.3',750),('R+rc2+EMA','×1.5 利確0.3',1000),
       ('R','×1.5 利確0.3',1000),('R','基準',1000),('R','基準',2000)]
STARTS=[int(np.searchsorted(idx.values,np.datetime64(x+'-01'))) for x in pd.period_range('2024-08','2026-03',freq='M').astype(str)]
def roll(a):
    ent,cn,K=a; out=[]
    for i0 in STARTS:
        for spr in (None,t.SPR*2):
            r=f.one((ent,cn,K,30,i0,spr)); out.append(r)
    return a,out
M=m5.M5(d)
def ev5(s):
    ev={}; t15=p.o.index.values
    for i in range(max(200,M.i0),d.N-1):
        k=int(s[i])
        if k==0 or not d.atr[i]>0: continue
        j=int(np.searchsorted(M.t,t15[i+1]))
        if j<len(M.t) and M.t[j]==t15[i+1]: ev.setdefault(j,[]).append((k,float(d.atr[i]),5.0))
    return ev
def m5run(a):
    ent,cn,K=a; out=[]
    e5=ev5(f.union(f.SETS[ent]))
    for spr in (None,t.SPR*2):
        r=sl.engine(M.O,M.H,M.L,M.C,e5,f.CF[cn],i0=1,comp=(E0,K,30),spr=spr); eqc=E0+r['eqc'][1:]*YEN; eqa=E0+r['eqa'][1:]*YEN; pk=np.maximum.accumulate(eqc)
        out.append((eqc[-1],((pk-eqa)/pk).max()*100,eqa.min()))
    return a,out
def boot(a):
    ent,cn,K=a; r0=sl.engine(d.O,d.H,d.L,d.C,f.EVS[ent],f.CF[cn],i0=200); tr=sorted(r0['trades'],key=lambda x:x[1]); pnl=np.array([x[0] for x in tr])*YEN
    rng=np.random.default_rng(1); n=len(pnl); B=20; res=[]
    for _ in range(1500):
        E=E0; peak=E; mdd=0; hit=None; k=0
        for st in rng.integers(0,n-B,size=n//B+1):
            for v in pnl[st:st+B]:
                m=max(1,min(30,int(E//K))); E+=v*m; k+=1
                if E<=0: E=0; break
                peak=max(peak,E); mdd=max(mdd,(peak-E)/peak)
                if hit is None and E>=3*E0: hit=k
            if E<=0: break
        res.append((E,mdd*100,hit if hit else np.nan,n))
    return a,np.array(res)
if __name__=='__main__':
    with Pool() as pl: RR=pl.map(roll,CANDS); MM=pl.map(m5run,CANDS); BB=pl.map(boot,CANDS)
    print('=== 1. 始点を毎月ずらす(2024-08〜2026-03 の20始点)')
    for a,out in RR:
        x=pd.DataFrame(out); u=x[~x.spr]; v=x[x.spr]
        print(f'{a[0]:<9}{a[1]:<10}K={a[2]:>4}: 3倍まで 中央値 {u.d3.median():.0f}日(到達 {int(u.d3.notna().sum())}/20、最長 {u.d3.max():.0f}日) 最終残高 中央値 {u.final.median():,.0f}円 最小 {u.final.min():,.0f}円 DD 中央値 {u.dd.median():.0f}% 最大 {u.dd.max():.0f}% | スプレッド2倍: 3倍まで 中央値 {v.d3.median():.0f}日(到達 {int(v.d3.notna().sum())}/20) 最終最小 {v.final.min():,.0f}円 DD最大 {v.dd.max():.0f}%')
    print('=== 2. M5(2026-04〜09、約5か月): 最終残高 / DD / 最小残高  [通常 | スプレッド2倍]')
    for a,out in MM:
        (f1,d1,m1),(f2,d2,m2)=out; print(f'{a[0]:<9}{a[1]:<10}K={a[2]:>4}: {f1:,.0f}円({100*(f1/E0-1):+.0f}%) DD{d1:.0f}% 最小{m1:,.0f}円 | {f2:,.0f}円({100*(f2/E0-1):+.0f}%) DD{d2:.0f}% 最小{m2:,.0f}円')
    print('=== 3. 取引順の入れ替え(ブロック20、1,500回、確定ベース)')
    for a,res in BB:
        fin=res[:,0]; dd=res[:,1]; hit=res[:,2]
        print(f'{a[0]:<9}{a[1]:<10}K={a[2]:>4}: 最終 中央値 {np.median(fin):,.0f} 5%点 {np.percentile(fin,5):,.0f} | DD中央値 {np.median(dd):.0f}% 95%点 {np.percentile(dd,95):.0f}% 50%超 {100*np.mean(dd>50):.1f}% 元本割れ {100*np.mean(fin<E0):.1f}% | 3倍までの取引数 中央値 {np.nanmedian(hit):.0f}回(到達 {100*np.mean(~np.isnan(hit)):.0f}%、全{int(res[0,3])}回中)')
