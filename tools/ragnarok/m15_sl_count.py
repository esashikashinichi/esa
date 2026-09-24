"""M15足(約2.2年)で、バスケット単位の金額損切り(既定10万円)が何回発動するかを数える。
backtest_ragnarok_abc_v2 / sl_study のルールを M15足に近似して使う。口座の証拠金・ロスカットは見ない(equity=None)。

M15足への近似:
  - 初弾の方向: 足の始値 − 1本前(15分前)の終値。a/b/c共通(M1の3/11/20分前は再現できない)
  - 初弾の発火率(--fire prob): M1(a はM5)1本あたりの実測発火率を、15分に1回以上発火する確率に換算
  - ナンピン: 1本(15分)に最大2回(420秒×2=14分)。2回目は足の安値(高値)がさらに100pts先まで届いた場合
  - 同じ足の中の順番は 初弾 → 利確 → ナンピン → 損切り(高値・安値のどちらが先かは不明)
ナンピン上限は 40(実機の設定)と 12(実測の最大。待機フィルターでレグ数が止まる場合の目安)の2通り。
使い方: python m15_sl_count.py GOLDmicro15.csv [M1_long.csv]
  2つ目を渡すと、重なる期間で M1モデルと M15近似の損切り回数を突き合わせる(近似の確認用)。
"""
import copy
import sys
from multiprocessing import Pool

import pandas as pd

import backtest_ragnarok_abc_v2 as bt
import sl_study as s

BAR_MIN = 15
SL_YEN = 100000
NANPIN_PER_BAR = 2            # 1本(15分)あたりのナンピン回数の上限


class M15Mixin:
    """Engine の初弾とナンピンを M15足用に置き換える"""

    def entries(self, t, bar):
        prev = self.prev_close.get(t)
        if prev is None:
            return
        mom = bar["open"] - prev
        if mom == 0:
            return
        d = 1 if mom > 0 else -1
        for grid, p in bt.GRIDS.items():
            key = (grid, d)
            if key in self.baskets:
                continue
            rate = 1 - (1 - p["fire_rate"]) ** (BAR_MIN / p["tf"])
            if self.fire == "prob" and self.rng.random() >= rate:
                continue
            if not self.can_afford(bt.BASE_LOT, bar["open"]):
                continue
            self.baskets[key] = bt.Basket(grid, d, t, bar["open"])
            self.last_entry[key] = t

    def nanpins(self, t, bar):
        for b in self.baskets.values():
            if b.legs >= self.max_legs or b.times[-1] >= t:
                continue
            level = b.last_bid - bt.NANPIN_MIN_ADVERSE * b.direction
            if not self.can_afford(bt.lot_for_leg(b.legs), bar["close"]):
                continue
            if (b.direction == 1 and bar["open"] <= level) or (b.direction == -1 and bar["open"] >= level):
                b.add_leg(t, bar["open"])
            elif (b.direction == 1 and bar["low"] <= level) or (b.direction == -1 and bar["high"] >= level):
                b.add_leg(t + pd.Timedelta(minutes=1), level)
            else:
                continue
            # 15分の中に420秒が2回入るので、足の安値(高値)がさらに100pts先まで届いていれば2回目
            if NANPIN_PER_BAR < 2 or b.legs >= self.max_legs:
                continue
            level2 = b.last_bid - bt.NANPIN_MIN_ADVERSE * b.direction
            if not self.can_afford(bt.lot_for_leg(b.legs), bar["close"]):
                continue
            if (b.direction == 1 and bar["low"] <= level2) or (b.direction == -1 and bar["high"] >= level2):
                b.add_leg(t + pd.Timedelta(minutes=8), level2)


class M15SLEngine(M15Mixin, s.SLEngine):
    def __init__(self, bars, **kw):
        super().__init__(bars, **kw)
        pc = bars["close"].shift(1)
        gap = bars.index.to_series().diff() <= pd.Timedelta(minutes=BAR_MIN)
        self.prev_close = pc[gap].to_dict()


class M15Engine(M15Mixin, bt.Engine):
    pass


def forward(bars, t0, b, max_legs):
    """損切りしなかった場合: バスケット単独でルールどおりに先まで進める(M15)"""
    b = copy.deepcopy(b)
    worst = b.floating_yen(bars.loc[t0, "close"])
    eng = M15Engine(bars.iloc[:1], max_legs=max_legs)
    eng.baskets = {("x", b.direction): b}
    for t, bar in bars.loc[t0:].iloc[1:].iterrows():
        level = b.tp_bid()
        if (bar["high"] >= level) if b.direction == 1 else (bar["low"] <= level):
            return dict(recovered=True, worst=worst, legs=b.legs, days=(t - t0).total_seconds() / 86400)
        eng.nanpins(t, bar)
        worst = min(worst, b.floating_yen(bar["low"] if b.direction == 1 else bar["high"]))
    return dict(recovered=False, worst=worst, legs=b.legs, days=None)


def run(args):
    bars, fire, seed, sl, engine, max_legs = args
    if engine == "m15":
        eng = M15SLEngine(bars, sl_yen=sl, sl_mode="per", fire=fire, seed=seed, equity=None, max_legs=max_legs)
    else:
        eng = s.SLEngine(bars, sl_yen=sl, sl_mode="per", fire=fire, seed=seed, equity=None, max_legs=max_legs)
    closed, _ = eng.run()
    ev = []
    for t, b, yen in eng.sl_events:
        f = forward(bars, t, b, max_legs) if engine == "m15" else s.forward(bars, t, b, max_legs)
        ev.append(dict(fire=f"{fire}{seed}", max_legs=max_legs, time=t, grid=b.grid, dir="buy" if b.direction == 1 else "sell",
                       open_time=b.open_time, legs=b.legs, lots=round(b.total_lots, 2), yen=yen,
                       recovered=f["recovered"], worst=round(f["worst"]), days_to_tp=f.get("days", (f.get("hours") or 0) / 24 if f["recovered"] else None)))
    tp = closed[closed.reason == "tp"] if len(closed) else closed
    summ = dict(fire=f"{fire}{seed}", engine=engine, max_legs=max_legs, sl_n=len(eng.sl_events), tp_n=len(tp),
                tp_yen=round(tp.profit_yen.sum()) if len(tp) else 0,
                sl_yen=round(sum(e[2] for e in eng.sl_events)))
    return summ, ev


FIRES = (("always", 0), ("prob", 0), ("prob", 1), ("prob", 2), ("prob", 3), ("prob", 4))

if __name__ == "__main__":
    m15 = bt.load_m1(sys.argv[1])
    if len(sys.argv) > 2:
        m1 = bt.load_m1(sys.argv[2])
        t0, t1 = max(m1.index[0], m15.index[0]), min(m1.index[-1], m15.index[-1])
        jobs = [(m15.loc[t0:t1], f, sd, SL_YEN, "m15", 40) for f, sd in FIRES] + \
               [(m1.loc[t0:t1], f, sd, SL_YEN, "m1", 40) for f, sd in FIRES]
        with Pool() as p:
            res = p.map(run, jobs)
        print(pd.DataFrame([r[0] for r in res]).to_string())
        sys.exit()
    with Pool() as p:
        res = p.map(run, [(m15, f, sd, SL_YEN, "m15", ml) for ml in (40, 12) for f, sd in FIRES])
    summ = pd.DataFrame([r[0] for r in res])
    ev = pd.DataFrame([e for r in res for e in r[1]])
    summ.to_csv("m15_sl_summary.csv", index=False)
    ev.to_csv("m15_sl_events.csv", index=False)
    print(summ.to_string())
