"""ナンピンの待機と M5 RSI(解析21の4節)

- 入力: EA_Monitor の ea_monitor_m1state.csv(毎分の指標とロジックごとの建玉)。
- 時間(420秒)と値幅(110pts)の条件が揃っている分だけを取り出し、次の1分でナンピンが入ったかを数える。
- RSI は逆行側から見た値にそろえる(売りの束はそのまま、買いの束は 100 − RSI)。
"""
import sys
import pandas as pd

d = pd.read_csv(sys.argv[1], sep=';')
d['t'] = pd.to_datetime(d.bar_time, format='mixed')
d = d.drop_duplicates('t', keep='last').sort_values('t').reset_index(drop=True)
rows = []
for lg in 'abc':
    for sd in ['buy', 'sell']:
        p = f'{lg}_{sd}_'
        L, S, A = d[p + 'legs'].values, d[p + 'sec_since_last'].values, d[p + 'adverse_pts'].values
        for i in range(len(d) - 1):
            if L[i] >= 1 and S[i] >= 420 and A[i] >= 110 and (d.t[i + 1] - d.t[i]).seconds == 60:
                r = d.iloc[i]
                rsi5 = r.m5_rsi14 if sd == 'sell' else 100 - r.m5_rsi14
                rows.append(dict(t=r.t, logic=lg, side=sd, legs=L[i], fired=L[i + 1] == L[i] + 1, rsi5=rsi5))
R = pd.DataFrame(rows)
print(len(R), 'minutes with conditions met,', R.fired.sum(), 'fired next minute')
g = R.groupby(pd.cut(R.rsi5, [0, 50, 60, 65, 70, 75, 100]), observed=False).fired.agg(['sum', 'count'])
g['rate'] = (g['sum'] / g['count']).round(3)
print(g.to_string())
print('fired rsi5:', R[R.fired].rsi5.quantile([0, .1, .5, .9, 1]).round(1).to_dict())
print('waited rsi5:', R[~R.fired].rsi5.quantile([0, .1, .5, .9, 1]).round(1).to_dict())
