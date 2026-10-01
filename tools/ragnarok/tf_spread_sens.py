"""解析57: スプレッドの感度(固定ドル 0.30/0.40/0.55/0.80/1.10)。推奨3候補(複利、1万円スタート)を M15 2.2年と M5 5か月で。
スプレッド(ドル)= usd / 期間の平均価格 を割合にして tf_sl4.engine の spr に渡す。tf_rank / tf_rank_m5 を前提(作業フォルダで実行)。"""
import numpy as np, tf_model as t, tf_sl4 as sl, tf_rank as r, tf_rank_m5 as q
d=r.d; M=q.M; E0=r.E0; YEN=t.YEN; pm=d.C.mean(); p5=M.C.mean()
CANDS=[('R または MACD押し(利確0.5)',1500),('R または MACD押し(pb2+H4)(利確0.3)',1000),('R + ピラミッディング2段(利確0.5)',1000)]
for usd in (0.30,0.40,0.55,0.80,1.10):
    out=[]
    for n,K in CANDS:
        s,c,sl0=r.C[n]
        x=sl.engine(d.O,d.H,d.L,d.C,r.ev(n),r.cf(c),i0=200,comp=(E0,K,30),spr=usd/pm); ec=E0+x['eqc'][200:]*YEN; ea=E0+x['eqa'][200:]*YEN; pk=np.maximum.accumulate(ec)
        y=sl.engine(M.O,M.H,M.L,M.C,q.ev5(n),r.cf(c),i0=1,comp=(E0,K,30),spr=usd/p5); e5=E0+y['eqc'][1:]*YEN; a5=E0+y['eqa'][1:]*YEN; p5k=np.maximum.accumulate(e5)
        out.append(f"M15 {ec[-1]:,.0f}円 DD{((pk-ea)/pk).max()*100:.0f}% | M5 {e5[-1]:,.0f}円 DD{((p5k-a5)/p5k).max()*100:.0f}%")
    print(f'スプレッド {usd:.2f}ドル:',' || '.join(out))
