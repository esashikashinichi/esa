"""解析40 第2段: 候補を M5 足(2026-04-13〜09-21)で答え合わせ。シグナル・ATR・損切り位置は M15 で作り、約定は M5 で追う。M1 は使わない。"""
import numpy as np, tf_model as t, tf_sl2 as sl
import tf_swing as w, tf_m5 as m5
d=w.d; o=w.o; M=m5.M5(d)
def ev5(s,sda):
    ev={}; t15=o.index.values
    for i in range(max(200,M.i0),d.N-1):
        k=int(s[i]);
        if k==0 or not d.atr[i]>0: continue
        sd=5.0 if sda is None else sda[i]
        if sd!=sd: continue
        j=int(np.searchsorted(M.t,t15[i+1]))
        if j<len(M.t) and M.t[j]==t15[i+1]: ev.setdefault(j,[]).append((k,float(d.atr[i]),float(sd)))
    return ev
def stat(r,i0,i1,days):
    return sl.summarize(r,i0,i1,[(i0,i1)],days)
def line(x): return f"n={x['n']:>4} 勝率{x['win']:.1f}% PF{x['pf']:.2f} 損益{x['pnl']:.0f}円 落込{x['dd']:.0f} 最大損{x['worst']:.0f} 損切り{x['sl_pct']:.1f}% 1日{x['epd']:.2f}回"
CFG=w.CFG
CANDS=[('R(固定5ATR)','R','R型',None),('R tp0.3 固定5','R','R型tp0.3',None),
 ('R tp0.3 H4n10 cap12 clip','R','R型tp0.3',('4h',10,0.0,12.0,'clip')),
 ('recross2 固定5','recross2','R型tp0.3',None),
 ('recross2 H4n3 cap6 clip','recross2','R型tp0.3',('4h',3,0.0,6.0,'clip')),
 ('recross2 H1n10 cap6 skip','recross2','R型tp0.3',('1h',10,0.0,6.0,'skip')),
 ('recross2 H4n2 cap6 skip','recross2','R型tp0.3',('4h',2,0.3,6.0,'skip')),
 ('recross14 ナンピン2+ピラ3 固定5','recross14','ナンピン2+ピラ3',None),
 ('recross14 ナンピン2+ピラ3 H4n5 cap6 clip','recross14','ナンピン2+ピラ3',('4h',5,0.0,6.0,'clip')),
 ('recross14 ナンピン2+ピラ3 H1n20 cap6 clip','recross14','ナンピン2+ピラ3',('1h',20,0.0,6.0,'clip')),
 ('recross14 R型 tp0.3 固定5','recross14','R型tp0.3',None)]
for name,en,cn,sp in CANDS:
    s=w.base_sig(en); sda=None if sp is None else w.sdarr(s,*sp); cfg=CFG[cn]
    r5=sl.engine(M.O,M.H,M.L,M.C,ev5(s,sda),cfg,i0=1); x5=stat(r5,1,len(M.O),M.days)
    r5b=sl.engine(M.O,M.H,M.L,M.C,ev5(s,sda),cfg,i0=1,spr=t.SPR*2); y5=stat(r5b,1,len(M.O),M.days)
    ev=sl.make_events(d,s,sda); r15=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=M.i0); x15=stat(r15,M.i0,d.N,M.days)
    print('==',name); print('  M5 :',line(x5)); print('  M5 スプレッド2倍:',line(y5)); print('  M15(同期間):',line(x15))
