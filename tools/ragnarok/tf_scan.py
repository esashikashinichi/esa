"""初弾の方向ルール: どの時間足の何本前の終値と比べると一番一致するか(解析20の追記)

- 入力: prior_extremes.py の出力(ENTRY行)と M1 足。
- n分足は M1 足から作る(0時起点で n 分ごとに区切る)。MT4 の iClose(Mn, j) と同じ位置の終値を取る。
- 比較する値段は約定価格(買い=ask、売り=bid)。差が0の件は数えない。
"""
import sys
import glob
import numpy as np
import pandas as pd
from prior_extremes import load_bars

bars_paths, events = sys.argv[1:-1], sys.argv[-1]
b = load_bars([p for g in bars_paths for p in sorted(glob.glob(g))])
c = b.c
ev = pd.read_csv(events, sep=None, engine='python')
e = ev[ev.event == 'ENTRY'].copy()
e['t'] = pd.to_datetime(e.time.str.replace('.', '-', regex=False))


def mn_close(t, n, j):
    end = t.floor(f'{n}min') - pd.Timedelta(minutes=n * (j - 1))
    return c.get(end - pd.Timedelta(minutes=1), np.nan)


rows = []
for lg in 'abc':
    x = e[e.logic == lg]
    for n in [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60]:
        shifts = [1, 2, 3, 4, 5, 8, 10, 11, 12, 15, 20, 30] if n == 1 else [1, 2, 3, 4]
        for j in shifts:
            ok = tot = 0
            for _, r in x.iterrows():
                ref = mn_close(r.t, n, j)
                if np.isnan(ref) or np.isnan(r.price):
                    continue
                d = r.price - ref
                if d == 0:
                    continue
                tot += 1
                ok += (d > 0) == (r.side == 'buy')
            if tot:
                rows.append((lg, n, j, ok, tot, ok / tot))
R = pd.DataFrame(rows, columns=['logic', 'tf_min', 'shift', 'ok', 'n', 'rate'])
for lg in 'abc':
    print(R[R.logic == lg].sort_values('rate', ascending=False).head(10).to_string(index=False))
    print(R[(R.logic == lg) & (R.tf_min.isin([3, 10, 30]))].to_string(index=False))
    print()
