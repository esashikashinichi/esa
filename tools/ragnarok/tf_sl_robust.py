"""解析38 第3段: 候補の頑健さ。年別・月別・スプレッド2倍・損切りのずれ・同時に1つだけ持つ場合・M5 足での答え合わせ、ロット別の金額"""
import tf_model as t, tf_sl as sl, tf_m5 as m5, numpy as np, pandas as pd
o=t.load_m15(); d=t.Data(o); DAYS=len(set(o.index.date)); M=m5.M5(d)
CANDS={
 'R rsi2+H4+ADX・ピラミッド2(損切り5)':('rsi2','h4adx',(0,1,1,2,1.0,1.0,0.5,0.3,4,5.0,0.1)),
 'R4.5 同(損切り4.5)':('rsi2','h4adx',(0,1,1,2,1.0,1.0,0.5,0.3,4,4.5,0.1)),
 'R3 同(損切り3)':('rsi2','h4adx',(0,1,1,2,1.0,1.0,0.5,0.3,4,3.0,0.1)),
 'D don100+H1H4・ピラミッド2(損切り12)':('don100','h1h4',(0,1,1,2,1.0,1.0,0.5,0.3,4,12.0,0.1)),
 'N pb_ema+H4・ナンピン2(損切り12)':('pb_ema','h4',(2,1,1.5,0,1,1,0.75,0.3,4,12.0,0.1)),
}
def line(x): return f"n={x['n']} 勝率{x['win']:.1f}% PF{x['pf']:.2f} 損益{x['pnl']:.0f}円 落込{x['dd']:.0f} 最大損{x['worst']:.0f} 損切り{x['sl_pct']:.1f}% 1日{x['epd']:.2f}回"
YR=[('2024後半','2024-07-23','2025-01-01'),('2025前半','2025-01-01','2025-07-01'),('2025後半','2025-07-01','2026-01-01'),('2026前半','2026-01-01','2026-05-01'),('2026夏〜','2026-05-01','2026-09-22')]
for name,(e,fl,cfg) in CANDS.items():
    s=t.apply_filter(d,t.signals(d,e),fl); ev=sl.make_events(d,s)
    r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200); full=sl.summarize(r,200,d.N,[(200,d.N)],DAYS)
    print('=====',name); print('  全期間:',line(full),f"期末の建玉{full['open_end']} 最大ロット{full['maxlot']:.0f}")
    for lab,a,b in YR:
        i0=max(200,int(np.searchsorted(o.index.values,np.datetime64(a)))); i1=int(np.searchsorted(o.index.values,np.datetime64(b)))
        x=sl.summarize(r,i0,i1,[(i0,i1)],len(set(o.index.date[i0:i1]))); print(f'  {lab}:',line(x))
    # 月別
    eq=pd.Series(r['eqc'][200:],index=o.index[200:]); mo=eq.groupby(eq.index.to_period('M')).last().diff(); mo.iloc[0]=eq.groupby(eq.index.to_period('M')).last().iloc[0]
    mo=mo*t.YEN; print(f'  月別: プラスの月 {int((mo>0).sum())}/{len(mo)}  最悪の月 {mo.min():.0f}円  最良の月 {mo.max():.0f}円  中央値 {mo.median():.0f}円')
    # 資金曲線が高値更新から戻るまでの最長日数
    ed=eq.groupby(eq.index.date).last(); pk=ed.cummax(); under=(ed<pk-1e-9).astype(int); best=cur=0
    for v in under:
        cur=cur+1 if v else 0; best=max(best,cur)
    print(f'  高値更新が止まった最長 {best}営業日')
    for lab,spr,slip in [('スプレッド2倍',t.SPR*2,0.1),('スプレッド3倍',t.SPR*3,0.1)]:
        r2=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,spr=spr); x=sl.summarize(r2,200,d.N,[(200,d.N)],DAYS); print(f'  {lab}:',line(x))
    for slip in (0.3,0.6):
        c=list(cfg); c[10]=slip; r2=sl.engine(d.O,d.H,d.L,d.C,ev,tuple(c),i0=200); x=sl.summarize(r2,200,d.N,[(200,d.N)],DAYS); print(f'  損切りのずれ{slip}ATR:',line(x))
    r3=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,both=False); x=sl.summarize(r3,200,d.N,[(200,d.N)],DAYS); print('  同時に1つだけ持つ:',line(x))
    x5=M.run(d,s,cfg); print('  M5足(2026-04〜09):',line(x5))
    i0=int(np.searchsorted(o.index.values,M.t[0]))+1; r4=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=i0); x15=sl.summarize(r4,i0,d.N,[(i0,d.N)],M.days); print('  M15足(同じ期間):',line(x15))
    yrs=(o.index[-1]-o.index[200]).days/365.25
    for lot in (0.01,0.03,0.05,0.10):
        mu=lot/0.01; print(f"   {lot}ロット: 年 {full['pnl']*mu/yrs:,.0f}円  最大の落ち込み {-full['dd']*mu:,.0f}円  1回の最大損 {full['worst']*mu:,.0f}円")
