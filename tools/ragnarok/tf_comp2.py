"""解析42 第2段: 複利の頑健さ(始点をずらす・取引順の入れ替え・スプレッド2倍・M5)。R(×1.0)。"""
import numpy as np, pandas as pd, tf_model as t, tf_sl4 as sl, tf_pyr as p, tf_m5 as m5, tf_pyr_m5 as q, tf_comp as c
d=p.d; o=p.o; E0=c.E0; YEN=t.YEN; cfg=c.CFG['R(×1.0)']; ev=p.ev('R'); idx=o.index
Ks=[(1000,30),(2000,30),(3000,30),(5000,30)]
print('=== 1. 始点をずらす(各始点から E0=1万円で複利。終了は最後まで)')
starts=['2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01']
for K,mm in Ks:
    row=[]
    for st in starts:
        i0=max(200,int(np.searchsorted(idx.values,np.datetime64(st)))); r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=i0,comp=(E0,K,mm))
        eqc,eqa,dd=c.curve(r,i0,d.N); yrs=(idx[-1]-idx[i0]).days/365.25
        row.append(f'{st[:7]}始: {eqc[-1]:,.0f}円(年{100*((eqc[-1]/E0)**(1/yrs)-1):.0f}% DD{dd:.0f}%)')
    print(f'K={K}(開始 {E0/K*0.01:.2f}lot):',' | '.join(row))
print('=== 2. スプレッド2倍(M15 全期間)')
for K,mm in Ks:
    r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,comp=(E0,K,mm),spr=t.SPR*2); eqc,eqa,dd=c.curve(r,200,d.N); print(f'K={K}: 最終 {eqc[-1]:,.0f}円 DD{dd:.0f}% 最小残高 {eqa.min():,.0f}円')
print('=== 3. M5 足(2026-04-13〜09-21、約5か月)')
M=q.M; s=p.entry('R'); e5=q.ev5(s)
for K,mm in Ks+[(10**9,1)]:
    for lab,spr in (('通常',None),('スプレッド2倍',t.SPR*2)):
        r=sl.engine(M.O,M.H,M.L,M.C,e5,cfg,i0=1,comp=(E0,K,mm),spr=spr); eqc=E0+r['eqc'][1:]*YEN; eqa=E0+r['eqa'][1:]*YEN; pk=np.maximum.accumulate(eqc)
        print(f'K={K if K<10**8 else "固定0.01"} {lab}: 最終 {eqc[-1]:,.0f}円 ({100*(eqc[-1]/E0-1):+.0f}%) DD{((pk-eqa)/pk).max()*100:.0f}% 最小残高 {eqa.min():,.0f}円')
print('=== 4. 取引順の入れ替え(ブロック20のブートストラップ 3,000回、確定ベースの残高)')
r0=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200); tr=sorted(r0['trades'],key=lambda x:x[1]); pnl=np.array([x[0] for x in tr])*YEN  # 0.01ロットあたり(円)
# 浮動を含む DD と確定ベース DD の比(固定0.01)
eq_c=E0+r0['eqc'][200:]*YEN; pkc=np.maximum.accumulate(eq_c); dd_float=((pkc-(E0+r0['eqa'][200:]*YEN))/pkc).max()
cl=E0+np.cumsum(pnl); pk=np.maximum.accumulate(cl); dd_closed=((pk-cl)/pk).max(); print(f'固定0.01: 浮動込み DD {dd_float*100:.1f}% / 確定ベース DD {dd_closed*100:.1f}%(比 {dd_float/dd_closed:.2f})')
rng=np.random.default_rng(1); n=len(pnl); B=20
def sim(K,mm):
    E=E0; peak=E; mdd=0; ruin=False
    for st in rng.integers(0,n-B,size=n//B+1):
        for v in pnl[st:st+B]:
            m=max(1,min(mm,int(E//K))); E+=v*m
            if E<=0: return 0,100,True
            peak=max(peak,E); mdd=max(mdd,(peak-E)/peak)
    return E,mdd*100,False
for K,mm in Ks:
    res=np.array([sim(K,mm) for _ in range(3000)]); fin=res[:,0]; dd=res[:,1]
    print(f'K={K}: 最終 中央値 {np.median(fin):,.0f}円 5%点 {np.percentile(fin,5):,.0f}円 95%点 {np.percentile(fin,95):,.0f}円 | 確定DD 中央値 {np.median(dd):.0f}% 95%点 {np.percentile(dd,95):.0f}% | DD50%超の割合 {100*np.mean(dd>50):.1f}% 元本割れ {100*np.mean(fin<E0):.1f}%')
