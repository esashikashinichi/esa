"""過去の売買ログとM1足から、EA_Monitor v3.7 のイベント記録(ea_monitor_events_v37.csv)と
同じ項目を再構成する。ティックが無いので、高値・安値はM1足で近似する。

出力(1行=1イベント、区切りは ;):
  ENTRY        初弾(_0)。3/11/20分前の終値との差、15分足2本前の終値との差(aの方向ルール)、
               直近5/15/60分の高値・安値、同じロジック・方向の
               前回初弾・前回決済からの秒数
  NANPIN       ナンピン(_1以降)。直前レグからの秒数、今の逆行幅、直前レグ以降の最大逆行(=直前の
               高値/安値)とその時刻、底からの戻り幅、時間と値幅の条件が揃った時刻と待ち時間
  BASKET_CLOSE バスケットの決済。平均建値からの決済幅、最後のレグ以降の最大含み益(MFE)と時刻、
               含み益が100ptsに達した時刻とその後の最小含み益
  OPEN_STATUS  最後の時点で決済されていないバスケットの、今時点の状態

使い方:
  python3 prior_extremes.py --log ea_monitor.csv --bars M1_long.csv GOLD_M1_20260922.csv ... \
      --out ragnarok_prior_extremes.csv

注意:
  - M1足はbid。買いの建値・逆行はask(=bid+スプレッド)、売りの決済はask で測る。
    スプレッドは各イベント行の spread_pts を使う。
  - 足の中の順番は分からないため、イベントの分の足は「その分の高値・安値を全部含む」扱い
    (最大逆行・MFEはやや大きめに出る)。足が無い時間(サーバー0時台など)は空欄。
  - ログの記録漏れ(レグ番号の飛び、CLOSEの欠落)は gap 列に印を付ける。
    CLOSEが1本も記録されていないバスケットは、M1足で利確ライン(1レグ70pts、2レグ以上140pts)
    +20ptsに届いた分で決済済みとみなし、gap=close_not_logged の行を出す。
"""
import argparse
import numpy as np
import pandas as pd

PT = 100.0            # 1ドル = 100pts
NANPIN_SEC = 420      # ナンピンの時間条件(解析19)
NANPIN_PTS = 110      # ナンピンの値幅条件(解析19)
PROBE_PTS = 100       # 早期決済の調査用: 含み益がこの幅に達した時刻を記録
MOM_MIN = (3, 11, 20)
TP_ONE = 70           # 1レグの利確幅(解析19)
TP_MULTI = 140        # 2レグ以上の利確幅(解析19)
TP_MARGIN = 20        # 足の中の上下で届いたように見える分の余裕


def load_bars(paths):
    out = []
    for p in paths:
        head = open(p, encoding='utf-8', errors='ignore').readline()
        x = pd.read_csv(p, header=0 if head.startswith('Date') else None)
        x = x.iloc[:, :6]
        x.columns = ['d', 'tm', 'o', 'h', 'l', 'c']
        x['t'] = pd.to_datetime(x.d.astype(str) + ' ' + x.tm.astype(str), format='%Y.%m.%d %H:%M')
        out.append(x[['t', 'o', 'h', 'l', 'c']])
    b = pd.concat(out).drop_duplicates('t', keep='last').set_index('t').sort_index()
    return b


def load_log(path):
    df = pd.read_csv(path, sep=';', usecols=range(22), dtype={'comment': str})
    df = df[df.event.isin(['OPEN', 'CLOSE', 'CLOSE_NOHIST'])].copy()
    df['t'] = pd.to_datetime(df.server_time, format='%Y.%m.%d %H:%M:%S')
    sp = df.comment.fillna('').str.split('_')
    df['logic'] = sp.str[0]
    df['k'] = pd.to_numeric(sp.str[1], errors='coerce')
    df = df[df.k.notna() & df.logic.str.fullmatch('[a-zA-Z]+')]
    df['k'] = df.k.astype(int)
    return df.sort_values(['t', 'ticket']).reset_index(drop=True)


class Bars:
    def __init__(self, b):
        self.b = b

    def window(self, t0, t1):
        """t0の分〜t1の分の足(両端を含む)"""
        return self.b.loc[t0.floor('min'):t1.floor('min')]

    def m15_close2(self, t):
        """判定の瞬間 t を含む15分足の、2本前の15分足の終値(MT4の iClose(M15, 2))"""
        start = t.floor('15min') - pd.Timedelta(minutes=30)
        w = self.b.loc[start:start + pd.Timedelta(minutes=14)]
        return w.c.iloc[-1] if len(w) else np.nan

    def close_before(self, t, minutes):
        """判定の瞬間 t から minutes 分前に始まった足の終値(b: 3分前 = 3本前の足)"""
        return self.b.c.get(t.floor('min') - pd.Timedelta(minutes=minutes), np.nan)

    def hilo_before(self, t, minutes):
        w = self.b.loc[t.floor('min') - pd.Timedelta(minutes=minutes):t.floor('min') - pd.Timedelta(minutes=1)]
        if len(w) == 0:
            return np.nan, np.nan
        return w.h.max(), w.l.min()


def side_sign(side):
    return 1 if side == 'buy' else -1


def adverse_path(bars, s, ref_px, sp, t0, t1):
    """t0〜t1 の各分で、ref_px(建値)からの逆行幅の最大(pts)。買いはask、売りはbidで測る"""
    w = bars.window(t0, t1)
    if len(w) == 0:
        return None
    if s == 1:
        adv = (ref_px - (w.l + sp)) * PT
    else:
        adv = (w.h - ref_px) * PT
    return adv


def fav_path(bars, s, avg, sp, t0, t1):
    """平均建値からの含み益(pts)の各分の最大/最小。買いはbid、売りはaskで決済する"""
    w = bars.window(t0, t1)
    if len(w) == 0:
        return None, None
    if s == 1:
        best = (w.h - avg) * PT
        worst = (w.l - avg) * PT
    else:
        best = (avg - (w.l + sp)) * PT
        worst = (avg - (w.h + sp)) * PT
    return best, worst


def build(log, bars, end_time):
    rows = []
    baskets = []                  # 進行中
    ticket_basket = {}
    last_entry = {}               # (logic, side) -> 時刻
    last_close = {}               # (logic, side) -> 時刻
    closed_ids = set()
    next_id = 1

    opens = log[log.event == 'OPEN']
    closes = log[log.event != 'OPEN']
    events = pd.concat([opens.assign(_o=0), closes.assign(_o=1)]).sort_values(['t', '_o', 'ticket'])

    def close_basket(bk, t, burst):
        s = bk['s']
        lots = np.array(bk['lots']); px = np.array(bk['px'])
        avg = (lots * px).sum() / lots.sum()
        cp = burst.close_price.mean()
        sp = bk['spread'][-1] / PT
        close_pts = s * (cp - avg) * PT
        t_last = bk['t'][-1]
        best, worst = fav_path(bars, s, avg, sp, t_last, t)
        r = dict(event='BASKET_CLOSE', time=t, logic=bk['logic'], side=bk['side'], basket=bk['id'],
                 legs=len(px), total_lots=round(lots.sum(), 2), avg_price=round(avg, 3),
                 close_price=round(cp, 3), close_pts=round(close_pts, 1),
                 profit_yen=round(burst.profit.sum(), 0),
                 sec_since_last_leg=(t - t_last).total_seconds(),
                 sec_since_first_leg=(t - bk['t'][0]).total_seconds())
        if best is not None:
            imfe = best.values.argmax()
            r.update(mfe_pts=round(best.iloc[imfe], 1), mfe_time=best.index[imfe],
                     sec_mfe_to_close=(t - best.index[imfe]).total_seconds(),
                     mae_pts=round(-worst.min(), 1))
            hit = best[best >= PROBE_PTS]
            if len(hit):
                th = hit.index[0]
                r.update(reach100_time=th, min_fav_after_reach100=round(worst.loc[th:].min(), 1))
        gaps = []
        if sorted(bk['k']) != list(range(len(bk['k']))):
            gaps.append('leg_missing')
        if len(burst) < len(px):
            gaps.append('close_missing')
        r['gap'] = ','.join(gaps)
        rows.append(r)

    pending_close = {}   # basket id -> list of close rows (同じバスケットの決済は数秒以内にまとまる)

    def flush_closes(now):
        for bid in list(pending_close):
            first_t = pending_close[bid][0].t
            if now is None or (now - first_t).total_seconds() > 10:
                burst = pd.DataFrame(pending_close.pop(bid))
                bk = next((b for b in baskets if b['id'] == bid), None)
                if bk is None:
                    continue
                close_basket(bk, burst.t.max(), burst)
                baskets.remove(bk)
                closed_ids.add(bid)
                last_close[(bk['logic'], bk['side'])] = burst.t.max()

    def prune_unrecorded(now):
        """CLOSEが丸ごと記録漏れのバスケットを、利確ラインに届いた時点で決済済みとみなす。
        (残したままだと、後のナンピンが古いバスケットに紐付いてしまう)"""
        for bk in list(baskets):
            if bk['id'] in pending_close:
                continue
            t_last = bk['t'][-1]
            if (now - t_last).total_seconds() < 120:
                continue
            lots = np.array(bk['lots']); px = np.array(bk['px'])
            avg = (lots * px).sum() / lots.sum()
            best, _ = fav_path(bars, bk['s'], avg, bk['spread'][-1] / PT,
                               t_last + pd.Timedelta(minutes=1), now - pd.Timedelta(minutes=1))
            if best is None or len(best) == 0:
                continue
            target = (TP_ONE if len(px) == 1 else TP_MULTI) + TP_MARGIN
            hit = best[best >= target]
            if len(hit):
                th = hit.index[0]
                rows.append(dict(event='BASKET_CLOSE', time=th, logic=bk['logic'], side=bk['side'],
                                 basket=bk['id'], legs=len(px), total_lots=round(lots.sum(), 2),
                                 avg_price=round(avg, 3), sec_since_last_leg=(th - t_last).total_seconds(),
                                 sec_since_first_leg=(th - bk['t'][0]).total_seconds(),
                                 gap='close_not_logged'))
                baskets.remove(bk)
                closed_ids.add(bk['id'])
                last_close[(bk['logic'], bk['side'])] = th

    for r in events.itertuples():
        flush_closes(r.t)
        prune_unrecorded(r.t)
        s = side_sign(r.type)
        key = (r.logic, r.type)
        sp = (r.spread_pts if pd.notna(r.spread_pts) else 50.0) / PT
        if r.event == 'OPEN':
            if r.k == 0:
                bk = dict(id=next_id, logic=r.logic, side=r.type, s=s, t=[r.t], px=[r.open_price],
                          lots=[r.lots], k=[0], spread=[r.spread_pts])
                next_id += 1
                baskets.append(bk)
                ticket_basket[r.ticket] = bk['id']
                row = dict(event='ENTRY', time=r.t, logic=r.logic, side=r.type, basket=bk['id'], leg=0,
                           price=r.open_price, bid=r.bid, ask=r.ask, spread_pts=r.spread_pts,
                           sec_since_prev_entry=(r.t - last_entry[key]).total_seconds() if key in last_entry else np.nan,
                           sec_since_prev_close=(r.t - last_close[key]).total_seconds() if key in last_close else np.nan)
                for m in MOM_MIN:
                    c = bars.close_before(r.t, m)
                    row[f'mom{m}_pts'] = round((r.bid - c) * PT, 1) if pd.notna(c) else np.nan
                c15 = bars.m15_close2(r.t)
                row['mom_m15c2_pts'] = round((r.bid - c15) * PT, 1) if pd.notna(c15) else np.nan
                pb = bars.b.loc[r.t.floor('min') - pd.Timedelta(minutes=1):r.t.floor('min') - pd.Timedelta(minutes=1)]
                if len(pb):
                    row.update(prev_bar_open=pb.o.iloc[0], prev_bar_high=pb.h.iloc[0],
                               prev_bar_low=pb.l.iloc[0], prev_bar_close=pb.c.iloc[0])
                for m in (5, 15, 60):
                    hi, lo = bars.hilo_before(r.t, m)
                    row[f'high{m}'] = hi
                    row[f'low{m}'] = lo
                last_entry[key] = r.t
                rows.append(row)
            else:
                cand = [b for b in baskets if b['logic'] == r.logic and b['side'] == r.type
                        and b['id'] not in pending_close]
                exact = [b for b in cand if b['k'][-1] == r.k - 1]
                pool = exact or cand
                gap = '' if exact else 'leg_missing'
                if not pool:
                    rows.append(dict(event='NANPIN', time=r.t, logic=r.logic, side=r.type, leg=r.k,
                                     price=r.open_price, gap='no_basket'))
                    continue
                bk = max(pool, key=lambda b: s * (b['px'][-1] - r.open_price))
                t_prev, px_prev = bk['t'][-1], bk['px'][-1]
                sp_prev = bk['spread'][-1] / PT
                row = dict(event='NANPIN', time=r.t, logic=r.logic, side=r.type, basket=bk['id'], leg=r.k,
                           price=r.open_price, bid=r.bid, ask=r.ask, spread_pts=r.spread_pts,
                           prev_leg_price=px_prev, prev_leg_time=t_prev,
                           sec_since_prev_leg=(r.t - t_prev).total_seconds(),
                           lot_ratio=round(r.lots / bk['lots'][-1], 3),
                           adv_now_pts=round(s * (px_prev - r.open_price) * PT, 1), gap=gap)
                adv = adverse_path(bars, s, px_prev, sp_prev, t_prev, r.t)
                if adv is not None and len(adv):
                    i = adv.values.argmax()
                    row.update(adv_max_pts=round(adv.iloc[i], 1), adv_max_time=adv.index[i])
                    # 直前レグ以降の高値・安値(bid)
                    w = bars.window(t_prev, r.t)
                    row.update(high_since_prev=w.h.max(), low_since_prev=w.l.min())
                    row['bounce_pts'] = round(row['adv_max_pts'] - row['adv_now_pts'], 1)
                    tmin = t_prev + pd.Timedelta(seconds=NANPIN_SEC)
                    ok = adv[(adv.index + pd.Timedelta(seconds=59) >= tmin) & (adv >= NANPIN_PTS)]
                    if len(ok):
                        tc = max(tmin, ok.index[0])
                        row.update(cond_met_time=tc, wait_sec=max(0.0, (r.t - tc).total_seconds()))
                bk['t'].append(r.t); bk['px'].append(r.open_price); bk['lots'].append(r.lots)
                bk['k'].append(r.k); bk['spread'].append(r.spread_pts)
                ticket_basket[r.ticket] = bk['id']
                rows.append(row)
        else:
            bid_ = ticket_basket.get(r.ticket)
            if bid_ is None or bid_ in closed_ids:
                continue
            pending_close.setdefault(bid_, []).append(r)
    flush_closes(None)

    # 今時点で決済されていないバスケット
    for bk in baskets:
        s = bk['s']
        lots = np.array(bk['lots']); px = np.array(bk['px'])
        avg = (lots * px).sum() / lots.sum()
        sp = bk['spread'][-1] / PT
        t_last, px_last = bk['t'][-1], bk['px'][-1]
        r = dict(event='OPEN_STATUS', time=end_time, logic=bk['logic'], side=bk['side'], basket=bk['id'],
                 legs=len(px), total_lots=round(lots.sum(), 2), avg_price=round(avg, 3),
                 prev_leg_price=px_last, prev_leg_time=t_last,
                 sec_since_prev_leg=(end_time - t_last).total_seconds(),
                 sec_since_first_leg=(end_time - bk['t'][0]).total_seconds())
        adv = adverse_path(bars, s, px_last, sp, t_last, end_time)
        if adv is not None and len(adv):
            i = adv.values.argmax()
            w = bars.window(t_last, end_time)
            r.update(adv_max_pts=round(adv.iloc[i], 1), adv_max_time=adv.index[i],
                     high_since_prev=w.h.max(), low_since_prev=w.l.min(),
                     last_bid=w.c.iloc[-1])
            r['adv_now_pts'] = round(s * (px_last - (w.c.iloc[-1] + (sp if s == 1 else 0))) * PT, 1)
            best, worst = fav_path(bars, s, avg, sp, t_last, end_time)
            r.update(mfe_pts=round(best.max(), 1), mae_pts=round(-worst.min(), 1),
                     fav_now_pts=round(s * ((w.c.iloc[-1] + (0 if s == 1 else sp)) - avg) * PT, 1))
        if sorted(bk['k']) != list(range(len(bk['k']))):
            r['gap'] = 'leg_missing'
        rows.append(r)
    return pd.DataFrame(rows)


COLS = ['event', 'time', 'logic', 'side', 'basket', 'leg', 'price', 'bid', 'ask', 'spread_pts',
        # ENTRY
        'mom3_pts', 'mom11_pts', 'mom20_pts', 'mom_m15c2_pts', 'prev_bar_open', 'prev_bar_high', 'prev_bar_low', 'prev_bar_close',
        'high5', 'low5', 'high15', 'low15', 'high60', 'low60', 'sec_since_prev_entry', 'sec_since_prev_close',
        # NANPIN / OPEN_STATUS
        'prev_leg_price', 'prev_leg_time', 'sec_since_prev_leg', 'lot_ratio', 'adv_now_pts', 'adv_max_pts',
        'adv_max_time', 'high_since_prev', 'low_since_prev', 'bounce_pts', 'cond_met_time', 'wait_sec',
        # BASKET_CLOSE / OPEN_STATUS
        'legs', 'total_lots', 'avg_price', 'close_price', 'close_pts', 'profit_yen', 'sec_since_last_leg',
        'sec_since_first_leg', 'mfe_pts', 'mfe_time', 'sec_mfe_to_close', 'mae_pts', 'reach100_time',
        'min_fav_after_reach100', 'last_bid', 'fav_now_pts', 'gap']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', required=True)
    ap.add_argument('--bars', nargs='+', required=True)
    ap.add_argument('--out', default='ragnarok_prior_extremes.csv')
    a = ap.parse_args()
    bars = Bars(load_bars(a.bars))
    log = load_log(a.log)
    end_time = min(log.t.max(), bars.b.index.max() + pd.Timedelta(seconds=59))
    df = build(log, bars, end_time)
    for c in COLS:
        if c not in df.columns:
            df[c] = np.nan
    df = df[COLS].sort_values(['time', 'event']).reset_index(drop=True)
    for c in ['time', 'prev_leg_time', 'adv_max_time', 'cond_met_time', 'mfe_time', 'reach100_time']:
        df[c] = pd.to_datetime(df[c]).dt.strftime('%Y.%m.%d %H:%M:%S')
    df.to_csv(a.out, sep=';', index=False, float_format='%.5g')
    print('log', log.t.min(), '->', log.t.max(), '| bars', bars.b.index.min(), '->', bars.b.index.max())
    print(df.event.value_counts().to_string())
    print('saved', a.out, len(df))


if __name__ == '__main__':
    main()
