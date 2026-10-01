"""解析36: 代表3手法の頑健さ(期間別・周辺の設定・スプレッド2倍・M1 での答え合わせ)"""
import tf_model as t, tf_m1check as mc, numpy as np, pandas as pd, itertools
o=t.load_m15(); d=mc.d
P=[np.datetime64(x) for x in ('2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01','2026-09-22')]
IDX=[int(np.searchsorted(o.index.values,x)) for x in P]
CANDS={
 'A ブレイク100本(フィルター無し)':('don100','none',dict(tp=0.5,sl=4,trail=4,frac=0.3)),
 'B RSI2押し目+H4+ADX':('rsi2','h4adx',dict(tp=0.5,sl=5,trail=4,frac=0.3)),
 'C EMA20押し目+H1・H4':('pb_ema','h1h4',dict(tp=0.75,sl=4,trail=4,frac=0.3)),
}
def per(s,kw):
    return [t.stats(t.simulate(d,s,'part',i0=a,i1=b,**kw)) for a,b in zip(IDX[:-1],IDX[1:])]
for name,(e,f,kw) in CANDS.items():
    s=t.apply_filter(d,t.signals(d,e),f)
    full=t.stats(t.simulate(d,s,'part',**kw))
    print('=====',name,e,f,kw); print('全期間',full)
    for lab,st in zip(['24H2','25H1','25H2','26-1~4','26-5~9'],per(s,kw)): print('  ',lab,'n',st['n'],'勝率',st['win'],'PF',st['pf'],'損益',st['total'],'最大落込',st['dd'])
    # 周辺: 1つずつ変える
    grid=dict(tp=[0.5,0.75,1.0],sl=[3,4,5,6],trail=[2,3,4,5],frac=[0.2,0.3,0.4,0.5])
    nb=[]
    for k_,vals in grid.items():
        for v in vals:
            kk=dict(kw); kk[k_]=v; st=t.stats(t.simulate(d,s,'part',**kk)); nb.append((k_,v,st['win'],st['pf'],st['total']))
    print('  周辺(1つずつ変更):',' '.join(f'{a}={b}:{c}%/PF{d_}' for a,b,c,d_,_ in nb))
    print('  周辺の勝率の最小',min(x[2] for x in nb),' PFの最小',min(x[3] for x in nb))
    # スプレッド2倍
    old=t.SPR; t.SPR=old*2; st2=t.stats(t.simulate(d,s,'part',**kw)); t.SPR=old
    print('  スプレッド2倍:',st2)
    # M1 答え合わせ(07-18〜09-21)
    A=t.stats(t.simulate(d,s,'part',i0=mc.I0,**kw)); B=t.stats(mc.sim_m1(s,'part',**kw))
    print('  M15計算(07-18〜):',A); print('  M1 計算(07-18〜):',B)
