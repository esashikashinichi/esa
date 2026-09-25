"""強いトレンドの間、M5 RSI(14) はどれくらい高いままでいるか(解析22)

- 入力: GOLDmicro の M5 足 CSV(日付,時刻,始値,高値,安値,終値,…、ヘッダー無し)。
- RSI はワイルダー方式(期間14)。
- 1) RSI が 70/75/80 を超えている時間の割合と、連続して超えている長さ。
- 2) 6時間で最も大きく上げた場面(重ならない上位12件)で、RSI が 75超 / 70超 / 60未満 だった時間の割合。
"""
import sys
import pandas as pd

x = pd.read_csv(sys.argv[1], header=None).iloc[:, :6]
x.columns = ['d', 't', 'o', 'h', 'l', 'c']
x.index = pd.to_datetime(x.d + ' ' + x.t, format='%Y.%m.%d %H:%M')
c = x.c
d = c.diff()
au = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
ad = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
r = 100 - 100 / (1 + au / ad)
print(x.index.min(), x.index.max(), len(x))
for th in [70, 75, 80]:
    a = (r > th).astype(int)
    g = (a.diff() != 0).cumsum()
    runs = a.groupby(g).agg(['first', 'size'])
    runs = runs[runs['first'] == 1]['size'] * 5
    print(th, 'share %', round(a.mean() * 100, 1), 'run min: median', runs.median(), 'p90', runs.quantile(.9), 'max', runs.max())
c6 = c.rolling(72).apply(lambda v: v[-1] - v[0], raw=True)
seen, ev = [], []
for t, v in c6.nlargest(400).items():
    if all(abs((t - s).total_seconds()) > 6 * 3600 for s in seen):
        seen.append(t)
        w = r[t - pd.Timedelta(hours=6):t]
        ev.append((t, round(v, 1), round((w > 75).mean() * 100), round((w > 70).mean() * 100), round((w < 60).mean() * 100), round(w.median(), 1)))
    if len(ev) >= 12:
        break
print('end move$ %>75 %>70 %<60 medianRSI')
for e in ev:
    print(*e)
