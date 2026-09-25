"""実機の3日間(09-22〜09-23の実ログ)に合わせてナンピン幅を調整し、そのモデルで2年分(M15足)を検証する。

1) 合わせ込み: 09-22 10:30〜09-24 0:00(サーバー時間)のM1足で、ナンピン幅(NANPIN_MIN_ADVERSE)を変えて
   バスケット数・決済益・最大含み損・最大ロット・最大レグ数を実機と比べる。
   実機: 234バスケット、決済益+29,096円、最大含み損−47,690円、最大31.6〜32.9lot、最大12レグ。
2) 2年分: GOLDmicro M15足(2024-07〜2026-09)で、調整したナンピン幅(2.00ドル)と元の幅(1.00ドル)を比べる。
   口座の証拠金は見ず(equity=None)、日ごと(日本時間7時区切り)の最大含み損を記録する。
   同じ期間(07-17〜09-21)はM1足モデルとも比べる。
使い方: python calib_3days.py GOLD_M1_20260922.csv GOLD_M1_20260923.csv M1_long.csv GOLDmicro15.csv
"""
import sys
from multiprocessing import Pool

import pandas as pd

import backtest_ragnarok_abc_v2 as bt
import m15_sl_count as m

W0, W1 = pd.Timestamp("2026-09-22 10:30"), pd.Timestamp("2026-09-24 00:00")
FIRES = [("prob", i) for i in range(5)]
ARGS = {}


class Recorder:
    """足ごとの含み損(買いは安値、売りは高値で評価)と建玉を記録する"""

    def account(self, t, bar):
        f = sum(b.floating_yen(bar["low"] if b.direction == 1 else bar["high"]) for b in self.baskets.values())
        self.rec.append((t, f, sum(b.total_lots for b in self.baskets.values())))
        super().account(t, bar)


class RecM15(Recorder, m.M15SLEngine):
    pass


class RecM1(Recorder, m.s.SLEngine):
    pass


def load_logger_m1(paths):
    d = pd.concat(pd.read_csv(p) for p in paths)
    d["t"] = pd.to_datetime(d.Date + " " + d.Time, format="%Y.%m.%d %H:%M")
    d = d.drop_duplicates("t").set_index("t").sort_index()
    return d.rename(columns=str.lower)[["open", "high", "low", "close"]]


def calib(a):
    step, fire, seed = a
    bt.NANPIN_MIN_ADVERSE = step
    bars = ARGS["win"].loc[W0 - pd.Timedelta(hours=2):W1]
    eng = m.s.SLEngine(bars, sl_yen=None, fire=fire, seed=seed, equity=None, max_legs=40, news=True)
    closed, _ = eng.run()
    tp = closed[closed.reason == "tp"]
    return dict(step=step, fire=f"{fire}{seed}", baskets=len(closed), profit=round(tp.profit_yen.sum()),
                worst=round(eng.stats["worst_float_yen"]), max_lots=round(eng.stats["max_lots"], 1),
                max_legs=int(closed.legs.max()))


def long_run(a):
    kind, step, fire, seed = a
    bt.NANPIN_MIN_ADVERSE = step
    m.NANPIN_PER_BAR = 2
    bars = ARGS["m15"] if kind == "m15" else ARGS["m1"]
    eng = (RecM15 if kind == "m15" else RecM1)(bars, sl_yen=None, fire=fire, seed=seed, equity=None,
                                                 max_legs=40, news=True)
    eng.rec = []
    closed, _ = eng.run()
    f = pd.DataFrame(eng.rec, columns=["t", "fl", "lots"]).set_index("t")
    f["day"] = (f.index - pd.Timedelta(hours=1)).normalize()        # サーバー1時=日本時間7時で区切る
    days = f.groupby("day").agg(worst=("fl", "min"), lots=("lots", "max"))
    tp = closed[closed.reason == "tp"]
    days["profit"] = tp.groupby((pd.to_datetime(tp.close_time) - pd.Timedelta(hours=1)).dt.normalize()).profit_yen.sum()
    days = days[days.index.dayofweek < 5].reset_index()
    days["kind"], days["step"], days["fire"] = kind, step, f"{fire}{seed}"
    return days


def episodes(days, th):
    """含み損が th 円を超えた日のうち、前日は超えていなかった日(=新しい発生)の数"""
    over = (days.sort_values("day").worst < -th).astype(int)
    return int(((over == 1) & (over.shift(fill_value=0) == 0)).sum())


def main():
    ARGS["win"] = load_logger_m1(sys.argv[1:3])
    ARGS["m1"] = bt.load_m1(sys.argv[3])
    ARGS["m15"] = bt.load_m1(sys.argv[4])
    with Pool() as p:
        cal = pd.DataFrame(p.map(calib, [(s, f, sd) for s in (1.0, 1.1, 1.3, 1.6, 1.8, 2.0, 2.2, 2.5) for f, sd in FIRES]))
        days = pd.concat(p.map(long_run, [(k, s, f, sd) for k, s in (("m15", 2.0), ("m15", 1.0), ("m1", 2.0))
                                          for f, sd in FIRES]))
    print(cal.groupby("step")[["baskets", "profit", "worst", "max_lots", "max_legs"]].median().to_string())
    days.to_csv("calib_3days_days.csv", index=False)
    for (kind, step), g in days.groupby(["kind", "step"]):
        per = g.groupby("fire").apply(lambda x: pd.Series({
            "days": len(x), "worst_median": x.worst.median(), "worst_p90": x.worst.quantile(0.1),
            "days_over_5man": (x.worst < -50000).sum(), "days_over_10man": (x.worst < -100000).sum(),
            "episodes_over_16man": episodes(x, 160000), "profit_median": x.profit.median()}))
        print(kind, step)
        print(per.median().round(0).to_string())


if __name__ == "__main__":
    main()
