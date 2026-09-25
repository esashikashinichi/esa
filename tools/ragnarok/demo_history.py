"""公開デモ口座の履歴(demo_ea_monitor_history_v38.csv)の解析(解析27)

入力: 1) 口座履歴 CSV(EA_Monitor v3.8 の書き出し)  2) GOLD の M1 足 CSV(複数可, M1HistoryLogger 形式)
      3) 任意: 本番の ea_monitor.csv 系(OPEN 行)を --real で複数指定すると、同じ時間帯の初弾を突き合わせる
出力: 標準出力に表。時刻はサーバー時間。
"""
import argparse, re
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('history')
ap.add_argument('m1', nargs='+')
ap.add_argument('--real', nargs='*', default=[])
a = ap.parse_args()

h = pd.read_csv(a.history, sep=';')
h['ot'] = pd.to_datetime(h.open_time, format='%Y.%m.%d %H:%M:%S')
h['ct'] = pd.to_datetime(h.close_time, format='%Y.%m.%d %H:%M:%S')
h['lg'] = h.comment.str.extract(r'^([a-e])_')[0]
h['n'] = h.comment.str.extract(r'_(\d+)')[0].astype(int)
h['buy'] = h.type == 'buy'
h = h.sort_values(['ot', 'ticket']).reset_index(drop=True)
print('注文', len(h), '件', h.ot.min(), '〜', h.ct.max())

m = pd.concat([pd.read_csv(f) for f in a.m1])
m['t'] = pd.to_datetime(m.Date + ' ' + m.Time, format='%Y.%m.%d %H:%M')
m = m.drop_duplicates('t').set_index('t').sort_index()
close1 = m.Close
print('M1 足', m.index.min(), '〜', m.index.max(), len(m), '本')

# ---- 束の組み立て(ロジック・方向ごと。_0 で新しい束、_k は最後の段が k-1 の束へ) ----
bid = np.zeros(len(h), int); nb = 0; openb = {}
for i, r in h.iterrows():
    key = (r.lg, r.buy)
    if r.n == 0:
        nb += 1; openb.setdefault(key, []).append([nb, 0]); bid[i] = nb
    else:
        cand = [b for b in openb.get(key, []) if b[1] == r.n - 1]
        b = cand[-1] if cand else (openb[key][-1] if openb.get(key) else None)
        if b is None:
            nb += 1; b = [nb, r.n - 1]; openb.setdefault(key, []).append(b)
        b[1] = r.n; bid[i] = b[0]
h['basket'] = bid

# ---- 1. 初弾: 判定の秒・方向ルール・同じ方向の再エントリー間隔 ----
e = h[h.n == 0].copy()
e['sec'] = e.ot.dt.second
e['bar'] = e.ot.dt.floor('min')
print('\n## 1. 初弾')
print(e.groupby('lg').agg(件数=('ticket', 'size'),
                          秒0から3=('sec', lambda s: int((s <= 3).sum())),
                          M5の頭=('ot', lambda t: int(((t.dt.minute % 5 == 0) & (t.dt.second <= 3)).sum()))).to_string())

def agree_m1(df, k):
    ref = close1.reindex(df.bar - pd.Timedelta(minutes=k)).values
    ok = ~np.isnan(ref)
    s = np.sign(df.open_price.values - ref)
    want = np.where(df.buy, 1, -1)
    return int((s[ok] == want[ok]).sum()), int(ok.sum())

m15 = m.resample('15min').agg({'Close': 'last'}).dropna()
def agree_m15(df, j):
    cur = df.ot.dt.floor('15min')
    ref = m15.Close.reindex(cur - pd.Timedelta(minutes=15 * j)).values
    ok = ~np.isnan(ref)
    s = np.sign(df.open_price.values - ref)
    want = np.where(df.buy, 1, -1)
    return int((s[ok] == want[ok]).sum()), int(ok.sum())

print('\n方向ルール(約定価格 と k本前のM1足の終値。上なら買い)の一致数: 上位3つ')
for lg, g in e.groupby('lg'):
    res = sorted([(agree_m1(g, k)[0] / max(1, agree_m1(g, k)[1]), k, *agree_m1(g, k)) for k in range(1, 31)], reverse=True)[:3]
    r15 = sorted([(agree_m15(g, j)[0] / max(1, agree_m15(g, j)[1]), j, *agree_m15(g, j)) for j in range(1, 5)], reverse=True)[:1]
    print(f'  {lg}: ' + ', '.join(f'M1 {k}本前 {x}/{n}' for _, k, x, n in res)
          + ' | ' + ', '.join(f'M15 {j}本前 {x}/{n}' for _, j, x, n in r15))

print('\n同じロジック・方向の初弾どうしの間隔(分): 最小・下から5番目')
for lg, g in e.groupby('lg'):
    gaps = []
    for _, s in g.groupby('buy'):
        d = s.ot.sort_values().diff().dt.total_seconds().dropna() / 60
        gaps += list(d)
    gaps = sorted(gaps)
    if gaps:
        print(f'  {lg}: 件数{len(gaps)} 最小 {gaps[0]:.2f} / 5番目 {gaps[min(4, len(gaps)-1)]:.2f}')

# ---- 2. ナンピン: 間隔・値幅・ロット倍率・同じ秒の同時ナンピン ----
print('\n## 2. ナンピン')
rows = []
for b, g in h.groupby('basket'):
    g = g.sort_values('n')
    for i in range(1, len(g)):
        p, c = g.iloc[i - 1], g.iloc[i]
        adv = (p.open_price - c.open_price) if c.buy else (c.open_price - p.open_price)
        rows.append(dict(lg=c.lg, n=c.n, ot=c.ot, sec=(c.ot - p.ot).total_seconds(), adv_pts=adv * 100,
                         ratio=c.lots / p.lots, lots=c.lots, prev_lots=p.lots))
N = pd.DataFrame(rows)
print('件数', len(N), ' 間隔(秒): 最小', N.sec.min(), ' 420未満', int((N.sec < 419).sum()),
      ' 420〜430', int(N.sec.between(419, 430).sum()), ' 中央値', N.sec.median())
print('逆行幅(pts, 約定価格どうし): 最小', round(N.adv_pts.min(), 1), ' 下位5%', round(N.adv_pts.quantile(.05), 1),
      ' 中央値', round(N.adv_pts.median(), 1))
print('段ごとのロット(最頻値):', h.groupby('n').lots.agg(lambda s: s.mode().iloc[0]).to_dict())
N['t_s'] = N.ot.dt.floor('s')
same = N.groupby(N.ot.dt.floor('2s')).lg.nunique()
print('2秒以内に複数ロジックが同時にナンピンした回数:', int((same >= 2).sum()), '/ ナンピンの時刻の数', len(same))

# ---- 3. 利確: 平均建値からの決済幅 ----
print('\n## 3. 束の決済')
B = []
for b, g in h.groupby('basket'):
    lots = g.lots.sum(); avg = (g.lots * g.open_price).sum() / lots
    cp = (g.lots * g.close_price).sum() / lots
    buy = g.buy.iloc[0]
    pts = ((cp - avg) if buy else (avg - cp)) * 100
    B.append(dict(basket=b, lg=g.lg.iloc[0], legs=len(g), maxn=g.n.max(), lots=lots, pts=pts, profit=g.profit.sum(),
                  span=(g.ct.max() - g.ct.min()).total_seconds(), start=g.ot.min(), end=g.ct.max()))
B = pd.DataFrame(B)
B['段'] = np.where(B.legs == 1, '1段', '2段以上')
print(B.groupby('段').pts.describe(percentiles=[.1, .5, .9]).round(1).to_string())
print('損失で終わった束:', int((B.profit < 0).sum()), '/', len(B))
print(B.groupby('lg').agg(束=('basket', 'size'), 最大段=('legs', 'max'), 損益=('profit', 'sum')).to_string())
print('\n大きい束(8段以上):')
print(B[B.legs >= 8].sort_values('start')[['lg', 'legs', 'lots', 'start', 'end', 'pts', 'profit']].to_string(index=False))

# ---- 4. 本番との突き合わせ(同じ時間帯の初弾) ----
if a.real:
    r = pd.concat([pd.read_csv(f, sep=';') for f in a.real])
    r = r[(r.event == 'OPEN') & r.magic.isin([848, 929])].copy()
    r['ot'] = pd.to_datetime(r.server_time, format='%Y.%m.%d %H:%M:%S')
    r = r.drop_duplicates('ticket')
    r['lg'] = r.comment.str.extract(r'^([a-e])_')[0]
    r['n'] = r.comment.str.extract(r'_(\d+)')[0].astype(float)
    r['buy'] = r.type == 'buy'
    lo, hi = max(r.ot.min(), h.ot.min()), min(r.ot.max(), h.ot.max())
    re0 = r[(r.n == 0) & r.ot.between(lo, hi)]
    de0 = e[e.ot.between(lo, hi) & e.lg.isin(['a', 'b', 'c'])]
    print(f'\n## 4. 本番との初弾の突き合わせ({lo} 〜 {hi})')
    for lg in 'abc':
        R = re0[re0.lg == lg]; D = de0[de0.lg == lg]
        hit = 0
        for _, x in R.iterrows():
            if ((D.buy == x.buy) & ((D.ot - x.ot).abs() <= pd.Timedelta(seconds=5))).any(): hit += 1
        print(f'  {lg}: 本番 {len(R)} / デモ {len(D)} / 5秒以内に同じ方向で両方にある {hit}')
