"""解析41 第2段: ピラミッディングの候補を M5 足(2026-04-13〜09-21)・スプレッド2倍・他の入口で答え合わせ。"""
import numpy as np, tf_model as t, tf_sl3 as sl, tf_pyr as p, tf_m5 as m5
d=p.d; o=p.o; M=m5.M5(d)
def ev5(s):
    ev={}; t15=o.index.values
    for i in range(max(200,M.i0),d.N-1):
        k=int(s[i])
        if k==0 or not d.atr[i]>0: continue
        j=int(np.searchsorted(M.t,t15[i+1]))
        if j<len(M.t) and M.t[j]==t15[i+1]: ev.setdefault(j,[]).append((k,float(d.atr[i]),5.0))
    return ev
def line(x): return f"n={x['n']:>4} 勝率{x['win']:.1f}% PF{x['pf']:.2f} 損益{x['pnl']:.0f}円 落込{x['dd']:.0f} 最大損{x['worst']:.0f} 最大ロット{x['maxlot']:.1f}"
C=p.cfg
CANDS=[('R基準(段2・幅1.0・×1.0・利確0.5)',C(2,1.0,1.0,0.5,0.3,4,0,0)),
 ('A 段2・幅1.0・×1.5・利確0.5',C(2,1.0,1.5,0.5,0.3,4,0,0)),
 ('B 段2・幅1.0・×0.5(逆ピラミッド)・利確0.3',C(2,1.0,0.5,0.3,0.3,4,0,0)),
 ('C 段4・幅1.0・×1.5・利確0.3・追いかけ6・建値ロック',C(4,1.0,1.5,0.3,0.3,6,1,0)),
 ('D 段4・幅1.5・×1.0・利確0.5・建値ロック',C(4,1.5,1.0,0.5,0.3,4,1,0)),
 ('E 段6・幅0.5・×1.5・利確0.75・追いかけ6・利確後も買い増し(損益最大)',C(6,0.5,1.5,0.75,0.3,6,0,1))]
s=p.entry('R'); ev=p.ev('R')
print('=== R 入口: M5 と M15 同期間 / スプレッド2倍')
for name,cfg in CANDS:
    r5=sl.engine(M.O,M.H,M.L,M.C,ev5(s),cfg,i0=1); x5=sl.summarize(r5,1,len(M.O),[(1,len(M.O))],M.days)
    r5b=sl.engine(M.O,M.H,M.L,M.C,ev5(s),cfg,i0=1,spr=t.SPR*2); y5=sl.summarize(r5b,1,len(M.O),[(1,len(M.O))],M.days)
    r15=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=M.i0); x15=sl.summarize(r15,M.i0,d.N,[(M.i0,d.N)],M.days)
    r15b=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,spr=t.SPR*2); y15=sl.summarize(r15b,200,d.N,[(200,d.N)],p.DAYS)
    print('==',name); print('  M5      :',line(x5)); print('  M5 spr2 :',line(y5)); print('  M15同期間:',line(x15)); print('  M15全期間 spr2:',line(y15))
print('=== 他の入口(M15 全期間): 基準 / ×1.5 / 建値ロック / 利確後も買い増し')
for en in ('EMA','rc2','rc14'):
    for lab,cfg in [('基準 段2・幅1.0・×1.0・利確0.5',C(2,1.0,1.0,0.5,0.3,4,0,0)),('×1.5',C(2,1.0,1.5,0.5,0.3,4,0,0)),('建値ロック 段4・×1.0',C(4,1.0,1.0,0.5,0.3,4,1,0)),('利確後も買い増し 段4',C(4,1.0,1.0,0.5,0.3,4,0,1)),('買い増し無し',C(0,1.0,1.0,0.5,0.3,4,0,0))]:
        x=p.run((en,cfg)); print(f"{en:>4} {lab:<24} N={x['N']:>4} PF{x['pf']:.2f} 損益{x['pnl']:.0f} 落込{x['dd']:.0f} 最大損{x['worst']:.0f} 前{x['pf_is']:.2f}/後{x['pf_oos']:.2f} 5期間+{x['pos5']}")
