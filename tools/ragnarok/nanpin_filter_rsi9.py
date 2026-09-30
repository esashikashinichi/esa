"""Ragnarok 解析29: ナンピンフィルターの特定(公開デモ口座・EA_Monitor v3.8 のログ)

入力(同じフォルダに置く、区切り ';'):
  events.csv  = demo_ea_monitor_events_v38.csv  (ENTRY / NANPIN / BASKET_CLOSE、オシレーター付き)
  wait.csv    = demo_ea_monitor_nanpin_wait_v38.csv (ナンピン条件を満たした後の10秒ごとの記録)
  m1state.csv = demo_ea_monitor_m1state.csv (毎分の close1 から M5 の足を作る)

やること:
  1. M5 RSI を 1分足の終値から作り直す(形成中の足 = 直前の確定足までの Wilder 平均 + 今の bid)。
     RSI(14) はログの m5_rsi0 と一致する(誤差 中央値0.003)ことで作り方を確認。
  2. 時間足 1/5/15/30/60分 × 期間 5〜28 の RSI で「逆行側の RSI <= T ならナンピン」の当てはまりを比べる。
     逆行側 = 売りの束は RSI、買いの束は 100-RSI。
     正例 = NANPIN の瞬間、負例 = 待機中(cond_now=1、発注の10秒より前)の記録。
  3. 1回目のナンピン(束が1段)と2回目以降で分けて確認。
  4. 1段の決済幅、d・e の初弾の向き。
"""
import numpy as np
import pandas as pd

KEY = ['logic', 'side', 'basket']


def load():
    e = pd.read_csv('events.csv', sep=';')
    w = pd.read_csv('wait.csv', sep=';')
    for d in (e, w):
        d['t'] = pd.to_datetime(d.time, format='%Y.%m.%d %H:%M:%S')
    n = e[e.event == 'NANPIN'].copy()
    idx = n.set_index(KEY + ['leg'])
    ft = [idx.loc[k, 't'] if k in idx.index else pd.NaT
          for k in zip(w.logic, w.side, w.basket, w.legs)]
    w['fire_t'] = pd.to_datetime(ft)
    w['to_fire'] = (w.fire_t - w.t).dt.total_seconds()
    return e, n, w


def m1_closes():
    m = pd.read_csv('m1state.csv', sep=';')
    fmt = '%Y.%m.%d %H:%M:%S' if len(m.bar_time.iloc[0]) > 16 else '%Y.%m.%d %H:%M'
    m['t'] = pd.to_datetime(m.bar_time, format=fmt)
    m = m.sort_values('t').drop_duplicates('t')
    # close1 の行 t は「t-1分に始まった M1 足」の終値
    return pd.Series(m.close1.values, index=m.t - pd.Timedelta(minutes=1))


C1 = None


def rsi_live(tf, p, times, prices):
    """形成中の足の RSI(MT4 の iRSI(..., shift 0) に相当)。"""
    global C1
    if C1 is None:
        C1 = m1_closes()
    cl = C1.groupby(C1.index.floor(f'{tf}min')).last()
    d = cl.diff()
    au = d.clip(lower=0).ewm(alpha=1 / p, adjust=False).mean()
    ad = (-d).clip(lower=0).ewm(alpha=1 / p, adjust=False).mean()
    out = []
    for t, pr in zip(times, prices):
        prev = t.floor(f'{tf}min') - pd.Timedelta(minutes=tf)
        if prev not in au.index:
            out.append(np.nan)
            continue
        dd = pr - cl[prev]
        a = (au[prev] * (p - 1) + max(dd, 0)) / p
        z = (ad[prev] * (p - 1) + max(-dd, 0)) / p
        out.append(100 * a / (a + z) if a + z > 0 else 50)
    return np.array(out)


def orient(v, side):
    return np.where(side == 'sell', v, 100 - v)


def main():
    e, n, w = load()
    W = w[(w.cond_now == 1) & (w.to_fire > 10)].copy()
    print('NANPIN', len(n), ' 待機中の記録', len(W))
    print('条件成立から10秒以内に発注:', round((n.wait_sec <= 10).mean(), 3))

    r = rsi_live(5, 14, n.t, n.bid)
    print('M5 RSI(14) 作り直しの誤差 p50/p90:', np.nanpercentile(np.abs(r - n.m5_rsi0), [50, 90]).round(3))

    res = []
    for tf in (1, 5, 15, 30, 60):
        for p in (5, 7, 9, 10, 12, 14, 16, 18, 20, 21, 24, 28):
            x1 = orient(rsi_live(tf, p, n.t, n.bid), n.side)
            x0 = orient(rsi_live(tf, p, W.t, W.bid), W.side)
            best = (0,)
            for T in np.arange(40, 90, 0.5):
                a, b = np.nanmean(x1 <= T), np.nanmean(x0 > T)
                if (a + b) / 2 > best[0]:
                    best = ((a + b) / 2, T, a, b)
            res.append((round(best[0], 3), tf, p, best[1], round(best[2], 3), round(best[3], 3)))
    res.sort(reverse=True)
    print('上位(平均の当たり, 時間足, 期間, 閾値, ナンピン側, 待機側)')
    for x in res[:8]:
        print(x)

    n['r9'] = orient(rsi_live(5, 9, n.t, n.bid), n.side)
    W['r9'] = orient(rsi_live(5, 9, W.t, W.bid), W.side)
    a, b = n[n.leg >= 2], W[W.legs >= 2]
    print('2回目以降のナンピン(束が2段以上):')
    for T in (64.5, 65, 65.5, 66):
        print(f'  T={T}: ナンピン {(a.r9 <= T).mean():.3f} ({len(a)})  待機 {(b.r9 > T).mean():.3f} ({len(b)})')
    f = n[n.leg == 1]
    print('1回目のナンピン: RSI(9)>65 で入った', int((f.r9 > 65).sum()), '/', len(f),
          ' 待ち時間 中央値', f.wait_sec.median())

    c = e[e.event == 'BASKET_CLOSE']
    print('1段の決済幅(pts):')
    print(c[c.legs == 1].groupby('logic').close_pts.describe()[['count', '25%', '50%', '75%']].round(0))
    print('2段以上の決済幅 中央値', c[c.legs >= 2].close_pts.median())

    en = e[e.event == 'ENTRY'].copy()
    s = np.where(en.side == 'buy', 1, -1)
    for col in ('mom3_pts', 'mom11_pts', 'mom20_pts', 'mom_m15c2_pts'):
        en[col] = (np.sign(en[col]) * s > 0)
    en['stoch_side'] = np.where(en.side == 'buy', en.m5_stoK0 < 50, en.m5_stoK0 > 50)
    print('初弾の向きと各指標の一致率')
    print(en.groupby('logic')[['mom3_pts', 'mom11_pts', 'mom20_pts', 'mom_m15c2_pts', 'stoch_side']].mean().round(2))


if __name__ == '__main__':
    main()
