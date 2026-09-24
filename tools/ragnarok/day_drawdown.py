"""実ログ(ea_monitor.csv)の建玉と M1足から、1分ごとの含み損(推定)とバスケットごとの最大含み損を出す。
バスケットは注文コメント(例: b_3)で組み立てる(_0 で新しいバスケット)。CLOSE の記録漏れは、
同じバスケットの最後の決済時刻、無ければ同じロジック・方向の次の初弾の時刻で決済したとみなす。
含み損は各M1足の最悪値(買いは安値、売りは高値+スプレッド)で見積もるため、実際よりやや大きめに出る。
使い方: python day_drawdown.py ea_monitor.csv 開始(サーバー時間) 終了 M1.csv [M1.csv ...]
  例: python day_drawdown.py ea_monitor.csv "2026-09-22 18:00" "2026-09-24 00:00" GOLD_M1_20260922.csv GOLD_M1_20260923.csv
"""
import sys

import pandas as pd

YEN_PER_DOLLAR_LOT = 157.4
SPREAD = 0.55
JST = pd.Timedelta(hours=6)          # 夏時間(サーバー+6時間)


def load_m1(paths):
    d = pd.concat(pd.read_csv(p) for p in paths)
    d["t"] = pd.to_datetime(d.Date + " " + d.Time, format="%Y.%m.%d %H:%M")
    return d.drop_duplicates("t").set_index("t").sort_index()


def load_legs(path, since):
    e = pd.read_csv(path, sep=";")
    e["t"] = pd.to_datetime(e.server_time, format="%Y.%m.%d %H:%M:%S")
    e = e[e.t >= since]
    o = e[e.event == "OPEN"].sort_values("t")
    rows, cur, bid = [], {}, 0
    for _, r in o.iterrows():
        logic, k = r.comment.split("_")
        key = (logic, r.type)
        if int(k) == 0 or key not in cur:
            bid += 1
            cur[key] = bid
        rows.append(dict(bid=cur[key], logic=logic, type=r.type, k=int(k), t=r.t, lots=r.lots,
                         price=r.open_price, ticket=r.ticket))
    legs = pd.DataFrame(rows)
    c = e[e.event.str.startswith("CLOSE")][["t", "ticket", "profit"]].rename(columns={"t": "tc"})
    legs = legs.merge(c, on="ticket", how="left")
    g = legs.groupby("bid").agg(start=("t", "min"), end=("tc", "max"), logic=("logic", "first"), type=("type", "first"))
    for b, r in g.iterrows():
        miss = (legs.bid == b) & legs.tc.isna()
        if not miss.any():
            continue
        if pd.notna(r.end):
            legs.loc[miss, "tc"] = r.end
        else:
            legs.loc[miss, "tc"] = g[(g.logic == r.logic) & (g.type == r.type) & (g.start > r.start)].start.min()
    legs["tc"] = legs.tc.fillna(pd.Timestamp.max)
    return legs


def floating(legs, bar):
    buy, sell = legs[legs.type == "buy"], legs[legs.type == "sell"]
    fb = ((bar.Low - buy.price) * buy.lots).sum()
    fs = ((sell.price - (bar.High + SPREAD)) * sell.lots).sum()
    return (fb + fs) * YEN_PER_DOLLAR_LOT


def main():
    ea, t0, t1 = sys.argv[1], pd.Timestamp(sys.argv[2]), pd.Timestamp(sys.argv[3])
    m1 = load_m1(sys.argv[4:])
    legs = load_legs(ea, t0 - pd.Timedelta(days=1))
    rows = []
    for t, bar in m1.loc[t0:t1].iterrows():
        op = legs[(legs.t < t + pd.Timedelta(minutes=1)) & (legs.tc > t + pd.Timedelta(seconds=59))]
        rows.append(dict(t=t, jst=t + JST, float=floating(op, bar), legs=len(op),
                         buy_lots=op[op.type == "buy"].lots.sum(), sell_lots=op[op.type == "sell"].lots.sum()))
    f = pd.DataFrame(rows).set_index("t")
    f["hour_jst"] = f.jst.dt.floor("h")
    hourly = f.groupby("hour_jst").agg(worst=("float", "min"), buy_lots=("buy_lots", "max"),
                                       sell_lots=("sell_lots", "max"), legs=("legs", "max"))
    px = m1.loc[t0:t1].copy()
    px["hour_jst"] = (px.index + JST).floor("h")
    ph = px.groupby("hour_jst").agg(open=("Open", "first"), high=("High", "max"), low=("Low", "min"), close=("Close", "last"))
    print(ph.join(hourly).round(1).to_string())
    out = []
    for b, x in legs.groupby("bid"):
        if x.k.max() < 4 or x.tc.max() < t0 or x.t.min() > t1:
            continue
        w = 0.0
        for t, bar in m1.loc[x.t.min().floor("min"):min(x.tc.max(), t1)].iterrows():
            w = min(w, floating(x[x.t < t + pd.Timedelta(minutes=1)], bar))
        out.append(dict(logic=x.logic.iloc[0], type=x.type.iloc[0], start_jst=x.t.min() + JST,
                        end_jst=x.tc.max() + JST, legs=x.k.max() + 1, lots=round(x.lots.sum(), 2),
                        worst_yen=round(w), profit_yen=x.profit.sum()))
    print(pd.DataFrame(out).to_string())


if __name__ == "__main__":
    main()
