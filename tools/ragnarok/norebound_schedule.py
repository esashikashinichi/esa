"""戻りの無い相場の回数と、10万円損切り・稼働停止(指標/月末月初/開場後/閉場前)の効果を2年分で比べる。

A) 戻りの無い相場: M15足の高値・安値で、途中の戻りが RETRACE ドル未満のまま一方向に動いた区間(ジグザグ)を数える。
   ラグナロクは平均建値から約+1.4ドル(実効ナンピン幅2ドルで約8〜10ドルの戻り)で利確するため、戻り10ドルを基準にした。
   区間の始まりが稼働停止の時間に入っているかも調べる。
B) 実機の3日間に合わせたモデル(ナンピン幅2.00ドル、解析17)で、次の6通りを比べる。
   稼働停止あり・なし × 損切りなし / 10万円損切り / 16万円ロスカット→再開
   稼働停止(新規の初弾だけ止める。持っているバスケットのナンピン・利確は続く):
     - 経済指標: 水 EIA原油在庫・木 新規失業保険・第1金 雇用統計・FOMC の120分前〜60分後(米東部時間で判定)
     - 月末最終営業日・月初第1営業日は1日中
     - 週末: 日本時間 土曜3:00〜月曜11:00(Shinさんの指定。毎日の閉場前・開場後は止めない)
   口座の証拠金は見ず、損切り(10万円)と「口座全体の含み損16万円でロスカット→同じ額で再開」の2通りで損益を数える。
   (口座171,638円そのものでは、どの方法でも2024-07-25にロスカットし、比べられないため)
使い方: python norebound_schedule.py GOLDmicro15.csv
"""
import sys
from multiprocessing import Pool

import pandas as pd

import backtest_ragnarok_abc_v2 as bt
import m15_sl_count as m

RETRACE = 10.0                                   # 戻りとみなす幅(ドル)
STEP = 2.00                                      # 解析17で合わせたナンピン幅
SL_YEN = 100000
STOPOUT_YEN = 160000                             # 口座約17〜20万円のロスカット水準
YEARS = 2.16
BLOCK = "5:3-24;6:0-24;0:0-11"                  # 日本時間 曜日(月=0):時-時。土曜3:00〜月曜11:00
FIRES = [("prob", i) for i in range(5)]
BARS = {}


def zigzag(bars, retrace):
    """戻りが retrace ドル未満のまま続いた一方向の区間(始点→極値)を返す。M15足の高値・安値で判定"""
    hi, lo, idx = bars["high"].values, bars["low"].values, bars.index
    out = []
    direction = 0
    start_i = ext_i = 0
    start_p = ext_p = bars["close"].iloc[0]
    for i in range(1, len(bars)):
        if direction == 0:
            if hi[i] - start_p >= retrace:
                direction, ext_i, ext_p = 1, i, hi[i]
            elif start_p - lo[i] >= retrace:
                direction, ext_i, ext_p = -1, i, lo[i]
        elif direction == 1:
            if hi[i] > ext_p:
                ext_i, ext_p = i, hi[i]
            elif ext_p - lo[i] >= retrace:
                out.append((idx[start_i], idx[ext_i], start_p, ext_p))
                start_i, start_p = ext_i, ext_p
                direction, ext_i, ext_p = -1, i, lo[i]
        else:
            if lo[i] < ext_p:
                ext_i, ext_p = i, lo[i]
            elif hi[i] - ext_p >= retrace:
                out.append((idx[start_i], idx[ext_i], start_p, ext_p))
                start_i, start_p = ext_i, ext_p
                direction, ext_i, ext_p = 1, i, hi[i]
    z = pd.DataFrame(out, columns=["start", "end", "p0", "p1"])
    z["move"] = z.p1 - z.p0
    z["hours"] = (z.end - z.start).dt.total_seconds() / 3600
    return z


def stop_reason(t, news, stop_days, block):
    j = bt.to_jst(t)
    if any(a <= t < b for a, b in news):
        return "指標"
    if (j - pd.Timedelta(hours=7)).normalize() in stop_days:
        return "月末月初"
    if (j.dayofweek, j.hour) in block:
        return "週末(土3時〜月11時)"
    return "その他"


def minute_index(bars):
    return pd.date_range(bars.index[0], bars.index[-1], freq="1min")


def run(a):
    """mode: none=損切りなし(口座無限) / sl10=バスケット単位10万円 / restart=口座全体16万円でロスカット→同額で再開"""
    sched, mode, fire, seed = a
    bt.NANPIN_MIN_ADVERSE = STEP
    m.NANPIN_PER_BAR = 2
    bars = BARS["m15"]
    sl, sl_mode = {"none": (None, "per"), "sl10": (SL_YEN, "per"), "restart": (STOPOUT_YEN, "total")}[mode]
    eng = m.M15SLEngine(bars, sl_yen=sl, sl_mode=sl_mode, fire=fire, seed=seed, equity=None, max_legs=40,
                        news=sched, block=bt.parse_block(BLOCK) if sched else None)
    if sched:
        eng.stop_days = bt.month_stop_days(minute_index(bars), 1)
    closed, _ = eng.run()
    tp = closed[closed.reason == "tp"] if len(closed) else closed
    sl_rows = closed[closed.reason == "sl"] if len(closed) else closed
    events = pd.Series([e[0] for e in eng.sl_events]).drop_duplicates()
    return dict(sched=sched, mode=mode, fire=f"{fire}{seed}", tp_yen=round(tp.profit_yen.sum()),
                loss_events=len(events), loss_yen=round(sl_rows.profit_yen.sum()) if len(sl_rows) else 0)


def main():
    bars = bt.load_m1(sys.argv[1])
    BARS["m15"] = bars
    mi = minute_index(bars)
    news, stop_days, block = bt.news_windows(mi), bt.month_stop_days(mi, 1), bt.parse_block(BLOCK)
    share = pd.Series([stop_reason(t, news, stop_days, block) for t in bars.index]).value_counts(normalize=True)
    print("時間の割合", share.round(3).to_dict())
    z = zigzag(bars, RETRACE)
    z["year"] = (z.start + pd.Timedelta(hours=6)).dt.year
    rows = []
    for th, h in ((30, 2), (40, 3), (60, 3), (80, 4)):
        x = z[(z.move.abs() >= th) & (z.hours >= h)].copy()
        x["reason"] = [stop_reason(t, news, stop_days, block) for t in x.start]
        r = dict(move=th, hours=h, count=len(x), per_year=round(len(x) / YEARS))
        r.update(x.year.value_counts().sort_index().to_dict())
        r.update(x.reason.value_counts(normalize=True).round(3).to_dict())
        rows.append(r)
    print(pd.DataFrame(rows).to_string())
    jobs = [(sc, mode, f, sd) for sc in (False, True) for mode in ("none", "sl10", "restart") for f, sd in FIRES]
    with Pool() as p:
        res = pd.DataFrame(p.map(run, jobs))
    res["net"] = res.tp_yen + res.loss_yen
    res.to_csv("norebound_schedule_result.csv", index=False)
    print(res.groupby(["sched", "mode"])[["tp_yen", "loss_events", "loss_yen", "net"]].median().to_string())


if __name__ == "__main__":
    main()
