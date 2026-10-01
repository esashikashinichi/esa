"""使うロジック(a/b/c)の組合せと口座額で、ロスカットの有無を比べる(初弾0.10固定、EAの最低ロット)。
使い方: python grid_subset_study.py M1_long.csv
"""
import sys
from multiprocessing import Pool

import pandas as pd
import backtest_ragnarok_abc_v2 as bt

ALL = dict(bt.GRIDS)
M1 = None


def run(args):
    grids, equity, fire, seed = args
    bt.GRIDS.clear()
    bt.GRIDS.update({g: ALL[g] for g in grids})
    eng = bt.Engine(M1, fire=fire, seed=seed, equity=equity, max_legs=40)
    closed, _ = eng.run()
    s = eng.stats
    tp = closed[closed.reason == "tp"] if len(closed) else closed
    return dict(grids=grids, equity=equity, fire=f"{fire}{seed}",
                stopout=s["stopout"][0] if s["stopout"] else None,
                balance=round(eng.balance), tp_yen=round(tp.profit_yen.sum()) if len(tp) else 0,
                min_level=round(s["min_level"][0], 3) if s["min_level"] else None,
                worst_float=round(s["worst_float_yen"]), max_lots=round(s["max_lots"], 2))


if __name__ == "__main__":
    M1 = bt.load_m1(sys.argv[1])
    jobs = [(g, eq, f, s) for g in ("abc", "ab", "bc", "ac", "a", "b", "c")
            for eq in (180901, 300000, 500000, 900000)
            for f, s in (("always", 0), ("prob", 0), ("prob", 1), ("prob", 2), ("prob", 3), ("prob", 4))]
    with Pool() as p:
        rows = p.map(run, jobs)
    df = pd.DataFrame(rows)
    df.to_csv("grid_subset_result.csv", index=False)
    print(df.to_string())
