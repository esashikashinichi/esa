"""
ラグナロク(Ragnarok EA) a/b/c 独立グリッド バックテスト v2
============================================================
セッション1版(legacy/backtest_ragnarok_abc_session1.py)を、
docs/ragnarok/analysis_02〜06 で検証したルールに置き換えたもの。

【反映済みのルール(実ログで検証済み)】
  初弾の方向   bid − k分前のM1足の終値 > 0 → 買い / < 0 → 売り
                 b: k=3(63/68) / c: k=11(41/46) / a: k=20(23/23)
  判定する足     b/c: M1足の始値 / a: M5足の始値
  再エントリー間隔(同じグリッド・同じ方向の初弾どうし)
                 b: 6分 / c: 9分 / a: 7.5分
  ナンピン       直前レグから420秒以上 かつ 直前レグ価格からbidで100pts以上逆行
  ロット         0.10 × 1.5^n(10レグ目まで)、11レグ目以降は ×1.2。発注時に0.01単位へ丸め
                 (0.10/0.15/0.23/0.34/0.51/0.76/1.14/1.71/2.56/3.84/4.61/5.54 が実測と一致)
  利確           加重平均建値から 1レグ +70pts / 2レグ以上 +140pts で全レグ一括決済
  約定           買いはask(=bid+スプレッド)、売りはbid。スプレッドは実測の中央値54pts

【未特定のため仮置きしている部分】
  - 初弾の発火条件: 方向・判定する足・再エントリー間隔の3条件を満たしても、実機は大半の足で見送る。
      --fire always : 条件を満たせば必ず入る(エントリー数・リスクとも最大側)
      --fire prob   : 実測の発火率(b 15% / c 7% / a 13%)でランダムに入る(--seed で固定)
  - ナンピンの待機フィルター(a/b/c共通。急騰急落中に止まる)は未実装。
    実機より早く・多くナンピンするため、含み損とロットは実機より大きめに出る。
    実ログの初弾で再現すると(--replay)、09-23未明の買いバスケットが実機10レグに対しモデル18レグとなり、
    実機が耐えた局面でモデルはロスカットする。破綻判定はこのフィルターの特定までは参考値。
    --max-legs で上限を実測最大(12)などに抑えた感度分析ができる。
  - 大ロットのバスケットが+140ptsより手前で決済される条件は未実装。
  - ロスカット判定は各M1足の終値で行う。XMのゼロカットは考慮しない(残高がマイナスで表示される場合あり)。

【モード】
  通常:    python3 backtest_ragnarok_abc_v2.py --m1 M1.csv [--fire always|prob]
  再現検証: python3 backtest_ragnarok_abc_v2.py --m1 M1.csv --replay ea_monitor.csv
           実ログの初弾(時刻・方向)をそのまま使い、ナンピンと利確だけをモデルで再現して、
           実際のバスケット(レグ数・ロット・決済時刻)と突き合わせる。
"""
import argparse
import math
import random

import numpy as np
import pandas as pd

POINT = 0.01
SPREAD = 0.54                 # ea_monitor.csv の spread_pts 中央値54pts
BASE_LOT = 0.10
LOT_MULT = 1.5
LOT_MULT_LATE = 1.2
LATE_FROM_LEG = 10            # 0始まりのレグ番号。10(=11レグ目)から×1.2
MAX_LEGS = 40                 # NanpinCount=40
NANPIN_MIN_SEC = 420
NANPIN_MIN_ADVERSE = 1.00     # 100pts
TP_1LEG = 0.70                # 70pts
TP_MULTI = 1.40               # 140pts
YEN_PER_DOLLAR_LOT = 157.4    # 1ドル×1lot の円換算(スクリーンショットの損益から逆算)
MARGIN_PER_LOT = 657.0        # 1lotあたりの必要証拠金(円、実測)
STOPOUT_LEVEL = 0.20          # XMのロスカット水準(証拠金維持率20%)

GRIDS = {
    #      比較する分  判定する足(分)  再エントリー間隔(秒)  実測の発火率
    "a": dict(k=20, tf=5, cooldown=450, fire_rate=23 / 171),
    "b": dict(k=3, tf=1, cooldown=360, fire_rate=63 / 419),
    "c": dict(k=11, tf=1, cooldown=540, fire_rate=40 / 583),
}


def lot_for_leg(n):
    """0始まりのレグ番号nのロット。倍率は丸める前の値に掛ける。"""
    raw = BASE_LOT * LOT_MULT ** min(n, LATE_FROM_LEG - 1)
    if n >= LATE_FROM_LEG:
        raw *= LOT_MULT_LATE ** (n - LATE_FROM_LEG + 1)
    return math.floor(raw * 100 + 0.5 + 1e-9) / 100


def load_m1(path):
    df = pd.read_csv(path, header=None, names=["date", "time", "open", "high", "low", "close", "volume"])
    df["t"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M")
    return df.drop_duplicates("t").sort_values("t").set_index("t")


class Basket:
    def __init__(self, grid, direction, t, bid):
        self.grid = grid
        self.direction = direction          # +1=買い, -1=売り
        self.open_time = t
        self.prices, self.lots, self.times = [], [], []
        self.worst_yen = 0.0
        self.add_leg(t, bid)

    def add_leg(self, t, bid):
        price = bid + SPREAD if self.direction == 1 else bid
        self.prices.append(price)
        self.lots.append(lot_for_leg(len(self.lots)))
        self.times.append(t)

    @property
    def legs(self):
        return len(self.prices)

    @property
    def total_lots(self):
        return sum(self.lots)

    @property
    def avg_price(self):
        return float(np.average(self.prices, weights=self.lots))

    @property
    def last_bid(self):
        """直前レグをbidに換算した価格(逆行幅はbidで測る)"""
        return self.prices[-1] - SPREAD if self.direction == 1 else self.prices[-1]

    def tp_bid(self):
        """決済できるbidの水準"""
        tp = TP_1LEG if self.legs == 1 else TP_MULTI
        if self.direction == 1:
            return self.avg_price + tp
        return self.avg_price - tp - SPREAD

    def floating_yen(self, bid):
        if self.direction == 1:
            diff = bid - self.avg_price
        else:
            diff = self.avg_price - (bid + SPREAD)
        return diff * self.total_lots * YEN_PER_DOLLAR_LOT

    def result(self, t, bid, reason):
        return dict(grid=self.grid, dir="buy" if self.direction == 1 else "sell",
                    open_time=self.open_time, close_time=t, legs=self.legs,
                    total_lots=round(self.total_lots, 2), avg_price=round(self.avg_price, 2),
                    close_bid=round(bid, 2), profit_yen=round(self.floating_yen(bid)),
                    worst_yen=round(self.worst_yen), reason=reason,
                    lots="/".join(f"{x:.2f}" for x in self.lots))


def us_dst(ts):
    """米国夏時間(3月第2日曜〜11月第1日曜)。XMのサーバー時間は夏GMT+3/冬GMT+2"""
    mar = pd.Timestamp(ts.year, 3, 1)
    start = mar + pd.Timedelta(days=(6 - mar.dayofweek) % 7 + 7)
    nov = pd.Timestamp(ts.year, 11, 1)
    end = nov + pd.Timedelta(days=(6 - nov.dayofweek) % 7)
    return start <= ts < end


def to_jst(ts):
    return ts + pd.Timedelta(hours=6 if us_dst(ts) else 7)


def parse_block(spec):
    """'2,3,4:20-24' → {(曜日, 時)}。曜日は日本時間の月=0〜日=6、時は日本時間。複数は ; 区切り"""
    out = set()
    if not spec:
        return out
    for part in spec.split(";"):
        days, hours = part.split(":")
        h0, h1 = (int(x) for x in hours.split("-"))
        for d in days.split(","):
            for h in range(h0, h1):
                out.add((int(d), h % 24))
    return out


def month_stop_days(m1_index, n):
    """月末・月初の営業日(日本時間7:00区切り、月〜金)を n 日ずつ返す"""
    if n <= 0:
        return set()
    tdays = sorted({(to_jst(t) - pd.Timedelta(hours=7)).normalize() for t in m1_index[::60]})
    tdays = [d for d in tdays if d.dayofweek < 5]
    by_month = {}
    for d in tdays:
        by_month.setdefault((d.year, d.month), []).append(d)
    out = set()
    for ym, ds in by_month.items():
        # 月の途中から/途中までのデータしか無い月は、端の日を月末・月初と誤認しないよう暦で判定
        last_cal = pd.Timestamp(ym[0], ym[1], 1) + pd.offsets.MonthEnd(0)
        bds = pd.bdate_range(pd.Timestamp(ym[0], ym[1], 1), last_cal)
        out.update(d for d in bds[:n] if d in ds)
        out.update(d for d in bds[-n:] if d in ds)
    return out


# 経済指標フィルターの近似(ラグナロク: StopMin=120 / StartMin=60 で新規の初弾だけ停止)
# 指標カレンダーが無いため、毎週決まって出る米指標だけで近似する。時刻は米東部時間(ET)。
# XMのサーバー時間は夏冬ともに ET+7時間。
FOMC_DATES = ["2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
              "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17",
              "2025-10-29", "2025-12-10",
              "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16",
              "2026-10-28", "2026-12-09"]
NEWS_STOP_BEFORE = 120
NEWS_START_AFTER = 60


def news_windows(m1_index):
    """(開始, 終了) のサーバー時間リスト。水 10:30 EIA原油在庫 / 木 8:30 新規失業保険 / 第1金 8:30 雇用統計 / FOMC 14:00"""
    events = []
    for day in pd.date_range(m1_index[0].normalize(), m1_index[-1].normalize()):
        if day.dayofweek == 2:
            events.append(day + pd.Timedelta(hours=10, minutes=30))
        if day.dayofweek == 3:
            events.append(day + pd.Timedelta(hours=8, minutes=30))
        if day.dayofweek == 4 and day.day <= 7:
            events.append(day + pd.Timedelta(hours=8, minutes=30))
        if day.strftime("%Y-%m-%d") in FOMC_DATES:
            events.append(day + pd.Timedelta(hours=14))
    out = []
    for et in events:
        srv = et + pd.Timedelta(hours=7)
        out.append((srv - pd.Timedelta(minutes=NEWS_STOP_BEFORE), srv + pd.Timedelta(minutes=NEWS_START_AFTER)))
    return out


class Engine:
    def __init__(self, m1, fire="always", seed=0, equity=None, replay_entries=None, max_legs=MAX_LEGS,
                 block=None, month_stop=0, news=False):
        self.m1 = m1
        self.block = block or set()
        self.stop_days = month_stop_days(m1.index, month_stop)
        self.blocked_entries = 0
        self.news = news_windows(m1.index) if news else []
        self.max_legs = max_legs
        self.close = m1["close"]
        self.fire = fire
        self.rng = random.Random(seed)
        self.baskets = {}                   # (grid, direction) -> Basket
        self.last_entry = {}                # (grid, direction) -> 直近の初弾時刻
        self.closed = []
        self.balance = equity
        self.replay = replay_entries        # {bar_time: [(grid, direction, t, 約定価格), ...]}
        self.stats = dict(worst_float_yen=0.0, worst_float_time=None, max_lots=0.0,
                          max_lots_time=None, min_level=None, stopout=None, rejected=0)

    def can_afford(self, lot, bid):
        """余剰証拠金が足りなければ発注できない(--equity 指定時のみ判定)"""
        if self.balance is None:
            return True
        floating = sum(b.floating_yen(bid) for b in self.baskets.values())
        used = sum(b.total_lots for b in self.baskets.values()) * MARGIN_PER_LOT
        if self.balance + floating - used >= lot * MARGIN_PER_LOT:
            return True
        self.stats["rejected"] += 1
        return False

    # --- 初弾 ---
    def entries(self, t, bar):
        if self.replay is not None:
            for grid, d, te, price in self.replay.get(t, []):
                key = (grid, d)
                if key in self.baskets:     # 実ログでは前のバスケットが決済済み。モデル側が未決済なら閉じる
                    b = self.baskets.pop(key)
                    self.closed.append(b.result(te, bar["open"], "replay_forced"))
                bid = price - SPREAD if d == 1 else price     # 実ログの約定価格(買いはask)をbidに換算
                self.baskets[key] = Basket(grid, d, te, bid)
            return
        if self.block or self.stop_days or self.news:
            j = to_jst(t)
            if ((j.dayofweek, j.hour) in self.block or (j - pd.Timedelta(hours=7)).normalize() in self.stop_days
                    or any(a <= t < b for a, b in self.news)):
                self.blocked_entries += 1
                return
        for grid, p in GRIDS.items():
            if t.minute % p["tf"]:
                continue
            ref_t = t - pd.Timedelta(minutes=p["k"])
            if ref_t not in self.close.index:
                continue
            mom = bar["open"] - self.close[ref_t]
            if mom == 0:
                continue
            d = 1 if mom > 0 else -1
            key = (grid, d)
            if key in self.baskets:
                continue
            last = self.last_entry.get(key)
            if last is not None and (t - last).total_seconds() < p["cooldown"]:
                continue
            if self.fire == "prob" and self.rng.random() >= p["fire_rate"]:
                continue
            if not self.can_afford(BASE_LOT, bar["open"]):
                continue
            self.baskets[key] = Basket(grid, d, t, bar["open"])
            self.last_entry[key] = t

    # --- 利確(足の高値・安値で判定し、利確水準で約定) ---
    def take_profits(self, t, bar):
        for key, b in list(self.baskets.items()):
            level = b.tp_bid()
            hit = bar["high"] >= level if b.direction == 1 else bar["low"] <= level
            if hit:
                fill = max(level, bar["open"]) if b.direction == 1 else min(level, bar["open"])
                self.closed.append(b.result(t, fill, "tp"))
                del self.baskets[key]

    # --- ナンピン ---
    def nanpins(self, t, bar):
        t_close = t + pd.Timedelta(minutes=1)
        for b in self.baskets.values():
            if b.legs >= self.max_legs:
                continue
            level = b.last_bid - NANPIN_MIN_ADVERSE * b.direction
            if not self.can_afford(lot_for_leg(b.legs), bar["close"]):
                continue
            if (t - b.times[-1]).total_seconds() >= NANPIN_MIN_SEC:
                # 足の始値の時点で420秒経過 → 足の中で水準に届いた瞬間に約定
                if (b.direction == 1 and bar["open"] <= level) or (b.direction == -1 and bar["open"] >= level):
                    b.add_leg(t, bar["open"])
                elif (b.direction == 1 and bar["low"] <= level) or (b.direction == -1 and bar["high"] >= level):
                    b.add_leg(t + pd.Timedelta(seconds=30), level)
            elif (t_close - b.times[-1]).total_seconds() >= NANPIN_MIN_SEC:
                # 足の途中で420秒に達する → 終値で判定
                if (b.direction == 1 and bar["close"] <= level) or (b.direction == -1 and bar["close"] >= level):
                    b.add_leg(t_close - pd.Timedelta(seconds=1), bar["close"])

    # --- 口座全体の含み損・ロスカット ---
    def account(self, t, bar):
        floating = 0.0
        lots = 0.0
        for b in self.baskets.values():
            f = b.floating_yen(bar["close"])
            b.worst_yen = min(b.worst_yen, f)
            floating += f
            lots += b.total_lots
        s = self.stats
        if floating < s["worst_float_yen"]:
            s["worst_float_yen"], s["worst_float_time"] = floating, t
        if lots > s["max_lots"]:
            s["max_lots"], s["max_lots_time"] = lots, t
        if self.balance is not None and lots > 0:
            level = (self.balance + floating) / (lots * MARGIN_PER_LOT)
            if s["min_level"] is None or level < s["min_level"][0]:
                s["min_level"] = (level, t)
            if level < STOPOUT_LEVEL and s["stopout"] is None:
                s["stopout"] = (t, round(floating), round(lots, 2))
                for key, b in list(self.baskets.items()):
                    self.closed.append(b.result(t, bar["close"], "stopout"))
                    del self.baskets[key]
                self.balance += floating

    def run(self):
        for t, bar in self.m1.iterrows():
            closed_before = len(self.closed)
            self.entries(t, bar)
            self.take_profits(t, bar)
            self.nanpins(t, bar)
            if self.balance is not None:
                self.balance += sum(c["profit_yen"] for c in self.closed[closed_before:]
                                    if c["reason"] in ("tp", "replay_forced"))
            self.account(t, bar)
            if self.stats["stopout"] is not None:
                break                       # 口座が破綻した時点で終了
        last_t, last_bar = self.m1.index[-1], self.m1.iloc[-1]
        open_rows = [b.result(last_t, last_bar["close"], "open") for b in self.baskets.values()]
        return pd.DataFrame(self.closed), pd.DataFrame(open_rows)


def summarize(closed, still_open, stats, span_days, balance=None, equity=None):
    tp = closed[closed.reason == "tp"] if len(closed) else closed
    print(f"決済済みバスケット: {len(tp)}件 ({len(tp) / span_days:.1f}件/日)")
    for g in GRIDS:
        sub = tp[tp.grid == g]
        if len(sub):
            print(f"  {g}: {len(sub)}件  平均レグ {sub.legs.mean():.2f}  最大レグ {sub.legs.max()}  "
                  f"利益 {sub.profit_yen.sum():,.0f}円")
    if len(tp):
        print(f"レグ数の分布: {tp.legs.value_counts().sort_index().to_dict()}")
        print(f"利確合計: {tp.profit_yen.sum():,.0f}円")
    if len(still_open):
        print(f"未決済バスケット: {len(still_open)}件  含み損益 {still_open.profit_yen.sum():,.0f}円")
        print(still_open[["grid", "dir", "open_time", "legs", "total_lots", "avg_price", "profit_yen"]].to_string(index=False))
    print(f"口座全体の最大含み損: {stats['worst_float_yen']:,.0f}円 ({stats['worst_float_time']})")
    print(f"最大合計ロット: {stats['max_lots']:.2f} ({stats['max_lots_time']})")
    if stats["min_level"] is not None:
        print(f"最低証拠金維持率: {stats['min_level'][0] * 100:.0f}% ({stats['min_level'][1]})")
    if stats["rejected"]:
        print(f"証拠金不足で見送った発注: {stats['rejected']}回")
    if stats["stopout"] is not None:
        t, f, lots = stats["stopout"]
        print(f"*** ロスカット発生: {t}  含み損 {f:,}円  合計 {lots}lot → ここで終了 ***")
    if balance is not None:
        print(f"口座: 開始 {equity:,.0f}円 → 終了時の確定残高 {balance:,.0f}円")


def load_replay(path, m1):
    e = pd.read_csv(path, sep=";")
    e["t"] = pd.to_datetime(e.server_time, format="%Y.%m.%d %H:%M:%S")
    e = e[(e.event == "OPEN") & e.comment.astype(str).str.match(r"^[abc]_\d+$")].copy()
    e["grid"] = e.comment.str[0]
    e["leg"] = e.comment.str.split("_").str[1].astype(int)
    e["d"] = np.where(e.type.astype(str).str.lower().str.contains("buy"), 1, -1)
    e = e[(e.t >= m1.index[0]) & (e.t <= m1.index[-1])]
    firsts = e[e.leg == 0]
    replay = {}
    for _, r in firsts.iterrows():
        replay.setdefault(r.t.floor("min"), []).append((r.grid, r.d, r.t, r.open_price))
    return replay, e


def compare_replay(closed, still_open, events):
    """実ログのバスケット(初弾〜次の初弾の直前)とモデルのバスケットを突き合わせる"""
    sim = pd.concat([closed, still_open], ignore_index=True)
    rows = []
    for (g, d), grp in events.groupby(["grid", "d"]):
        grp = grp.sort_values("t")
        starts = grp[grp.leg == 0].t.tolist()
        for i, st in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else pd.Timestamp.max
            legs = grp[(grp.t >= st) & (grp.t < end)]
            s = sim[(sim.grid == g) & (sim.dir == ("buy" if d == 1 else "sell")) & (sim.open_time == st)]
            if not len(s):
                continue
            s = s.iloc[0]
            rows.append(dict(grid=g, dir="buy" if d == 1 else "sell", start=st,
                             real_legs=int(legs.leg.max()) + 1, sim_legs=int(s.legs),
                             real_last_lot=float(legs.sort_values("t").lots.iloc[-1]),
                             sim_lots=s.lots.split("/")[-1], sim_close=s.close_time, sim_reason=s.reason,
                             next_start=None if end == pd.Timestamp.max else end))
    r = pd.DataFrame(rows)
    r["legs_match"] = r.real_legs == r.sim_legs
    print(f"突き合わせたバスケット: {len(r)}件  レグ数一致: {r.legs_match.sum()}件 ({r.legs_match.mean() * 100:.0f}%)")
    print(f"  モデルのほうが多い: {(r.sim_legs > r.real_legs).sum()}件 / 少ない: {(r.sim_legs < r.real_legs).sum()}件")
    ok = r[r.sim_reason == "tp"]
    early = ok[ok.next_start.notna() & (ok.sim_close <= ok.next_start)]
    print(f"  モデルが利確したバスケットのうち、実ログの次の初弾より前に決済: {len(early)}/{len(ok)}")
    diff = r[~r.legs_match]
    if len(diff):
        print("レグ数が違うバスケット:")
        print(diff[["grid", "dir", "start", "real_legs", "sim_legs", "sim_reason"]].to_string(index=False))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m1", required=True, help="M1足CSV(MT4形式: date,time,open,high,low,close,volume)")
    ap.add_argument("--fire", choices=["always", "prob"], default="always")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--equity", type=float, default=None, help="口座の有効証拠金(円)。指定するとロスカットを判定")
    ap.add_argument("--max-legs", type=int, default=MAX_LEGS,
                    help="レグ数の上限(感度分析用。実機の設定は40、実測の最大は12)")
    ap.add_argument("--replay", default=None, help="ea_monitor.csv を指定すると再現検証モード")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--block", default=None,
                    help="新規の初弾を止める曜日・時間(日本時間)。例 '2,3,4:20-24' = 水木金の20〜24時。';'で複数")
    ap.add_argument("--month-stop", type=int, default=0,
                    help="月末・月初の営業日を各N日、新規の初弾を止める(日本時間7:00区切り)")
    ap.add_argument("--news", action="store_true",
                    help="経済指標の新規停止(120分前〜60分後)を近似で入れる(水EIA・木失業保険・第1金雇用統計・FOMC)")
    args = ap.parse_args()

    m1 = load_m1(args.m1)
    if args.start:
        m1 = m1[m1.index >= pd.Timestamp(args.start)]
    if args.end:
        m1 = m1[m1.index <= pd.Timestamp(args.end)]
    span_days = max((m1.index[-1] - m1.index[0]).total_seconds() / 86400, 1e-9)
    print(f"M1データ: {m1.index[0]} 〜 {m1.index[-1]} ({span_days:.1f}日, {len(m1)}本)")

    if args.replay:
        replay, events = load_replay(args.replay, m1)
        eng = Engine(m1, replay_entries=replay, equity=args.equity, max_legs=args.max_legs)
        closed, still_open = eng.run()
        summarize(closed, still_open, eng.stats, span_days, eng.balance, args.equity)
        compare_replay(closed, still_open, events)
    else:
        print(f"初弾の発火: {args.fire}" + (f" (seed={args.seed})" if args.fire == "prob" else ""))
        eng = Engine(m1, fire=args.fire, seed=args.seed, equity=args.equity, max_legs=args.max_legs,
                     block=parse_block(args.block), month_stop=args.month_stop, news=args.news)
        if args.block or args.month_stop or args.news:
            print(f"新規停止: 曜日・時間={args.block or 'なし'} / 月末月初={args.month_stop}日 / 指標={'あり' if args.news else 'なし'} "
                  f"(対象日: {', '.join(d.strftime('%m-%d') for d in sorted(eng.stop_days)) or 'なし'})")
        closed, still_open = eng.run()
        summarize(closed, still_open, eng.stats, span_days, eng.balance, args.equity)
        if args.block or args.month_stop or args.news:
            print(f"停止で見送った判定回数(分): {eng.blocked_entries}")


if __name__ == "__main__":
    main()
