"""ea_monitor_equity.csv(1分ごとの残高・有効証拠金)から、実際の含み損を時間帯ごとに出す。
実際の含み損 = 有効証拠金 − 残高 − クレジット(XMのボーナス)。クレジットは建玉0の行の(有効証拠金 − 残高)で求める。
使い方: python equity_day.py ea_monitor_equity.csv 開始(日本時間) 終了
  例: python equity_day.py ea_monitor_equity.csv "2026-09-22 07:00" "2026-09-24 07:00"
"""
import sys

import pandas as pd

JST = pd.Timedelta(hours=6)          # 夏時間(サーバー+6時間)
COLS = ["server_time", "local_time", "balance", "equity", "margin", "free_margin", "margin_level_pct",
        "open_positions", "open_lots", "floating_pnl_all", "drawdown_from_peak_pct", "num_baskets", "extra"]


def load(path):
    q = pd.read_csv(path, sep=";", names=COLS, skiprows=1)      # 途中から列が1つ増えている
    q["t"] = pd.to_datetime(q.server_time, format="%Y.%m.%d %H:%M:%S")
    q["jst"] = q.t + JST
    credit = (q.equity - q.balance)[q.open_positions == 0].median()
    q["floating"] = q.equity - q.balance - credit
    return q, credit


def main():
    q, credit = load(sys.argv[1])
    t0, t1 = pd.Timestamp(sys.argv[2]), pd.Timestamp(sys.argv[3])
    x = q[(q.jst >= t0) & (q.jst < t1)]
    print(f"クレジット {credit:,.0f}円 / 記録 {x.jst.min()} 〜 {x.jst.max()}")
    h = x.groupby(x.jst.dt.floor("h")).agg(
        positions=("open_positions", "max"), lots=("open_lots", "max"), worst=("floating", "min"),
        balance=("balance", "last"), min_margin_level=("margin_level_pct", lambda s: s[s > 0].min()))
    print(h.to_string())
    i = x.floating.idxmin()
    print(f"最大含み損 {x.floating.min():,.0f}円  {x.loc[i, 'jst']}  {x.loc[i, 'open_lots']}lot  "
          f"維持率 {x.loc[i, 'margin_level_pct']:.0f}%  残高の増減 {x.balance.iloc[-1] - x.balance.iloc[0]:+,.0f}円")


if __name__ == "__main__":
    main()
