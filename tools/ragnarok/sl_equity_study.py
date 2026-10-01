"""損切り10万円(バスケット単位/口座全体)を、口座50万・90万円で損切りなしと比べる。
使い方: python sl_equity_study.py M1_long.csv
"""
import sys
from multiprocessing import Pool

import pandas as pd
import backtest_ragnarok_abc_v2 as bt
import sl_study as s

M1 = None


def run(args):
    sl, mode, equity, fire, seed = args
    r = s.run(M1, sl, mode, fire, seed, equity=equity)
    r["equity"] = equity
    return r


if __name__ == "__main__":
    M1 = bt.load_m1(sys.argv[1])
    jobs = [(sl, mode, eq, f, sd) for eq in (500000, 900000)
            for sl, mode in ((None, "per"), (100000, "per"), (100000, "total"))
            for f, sd in (("always", 0), ("prob", 0), ("prob", 1), ("prob", 2), ("prob", 3), ("prob", 4))]
    with Pool() as p:
        rows = p.map(run, jobs)
    df = pd.DataFrame(rows)
    df.to_csv("sl100k_equity_result.csv", index=False)
    print(df[["equity", "sl", "mode", "fire", "stopout", "balance", "sl_n", "sl_yen", "rec_n", "rec_worst"]].to_string())
