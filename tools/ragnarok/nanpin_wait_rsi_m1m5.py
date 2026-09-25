"""ナンピンの待機: M5 RSI と M1 RSI の両方を見ているか(解析25)

- 入力: EA_Monitor の ea_monitor_m1state.csv(複数可。毎分の指標とロジックごとの建玉)。
- 時間(420秒)と値幅(110pts)の条件が揃っている分だけを取り出し、次の1分でナンピンが入ったかを数える。
- a/b/c は同じ秒で待ち・入るため、同じ分・同じ方向は1件にまとめる。
- RSI は逆行側から見た値にそろえる(売りの束はそのまま、買いの束は 100 − RSI)。
- M5 だけ / M1 だけ / 両方 のしきい値ルールで、何件を正しく説明できるかを比べる。
"""
import sys
import pandas as pd

d = pd.concat([pd.read_csv(f, sep=';') for f in sys.argv[1:]])
d['t'] = pd.to_datetime(d.bar_time, format='mixed')
d = d.drop_duplicates('t', keep='last').sort_values('t').reset_index(drop=True)
rows = []
for lg in 'abc':
    for sd in ['buy', 'sell']:
        p = f'{lg}_{sd}_'
        L, S, A = d[p + 'legs'].values, d[p + 'sec_since_last'].values, d[p + 'adverse_pts'].values
        for i in range(len(d) - 1):
            if L[i] >= 1 and S[i] >= 420 and A[i] >= 110 and (d.t[i + 1] - d.t[i]).seconds == 60:
                r, n = d.iloc[i], d.iloc[i + 1]
                f = (lambda x: x) if sd == 'sell' else (lambda x: 100 - x)
                rows.append(dict(t=r.t, side=sd, fired=L[i + 1] == L[i] + 1,
                                 r5=f(r.m5_rsi14), r1=f(r.m1_rsi14), r1n=f(n.m1_rsi14)))
U = pd.DataFrame(rows).groupby(['t', 'side']).agg(
    fired=('fired', 'max'), r5=('r5', 'first'), r1=('r1', 'first'), r1n=('r1n', 'first')).reset_index()
print(d.t.min(), '〜', d.t.max(), '/ 条件が揃った分(方向別):', len(U), '/ 次の1分で入った:', U.fired.sum())

b5 = pd.cut(U.r5, [0, 50, 60, 70, 75, 100])
b1 = pd.cut(U.r1n, [0, 50, 60, 100])
print('\nM5 RSI × M1 RSI(次の分の値)→ 入った数 / 件数')
t = U.groupby([b5, b1], observed=True).fired.agg(['sum', 'count'])
print(t.to_string())


def score(pred):
    return int((pred == U.fired).sum()), int((pred & ~U.fired).sum()), int((~pred & U.fired).sum())


m5 = max((score(U.r5 <= a) + (a,)) for a in range(45, 80))
m1 = max((score(U.r1 <= a) + (a,)) for a in range(30, 80))
both = max((score((U.r5 <= lo) | ((U.r5 <= hi) & (U.r1 <= z))) + (lo, hi, z))
           for lo in range(45, 65) for hi in range(lo, 80) for z in range(40, 75))
print('\n正解数, 入ると予測して待った, 待つと予測して入った, しきい値')
print('M5 だけ    :', m5)
print('M1 だけ    :', m1)
print('M5+M1 両方 :', both)
