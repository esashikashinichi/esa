"""
金額ロスカット(円)の検証。backtest_ragnarok_abc_v2.py のモデルに、次の2種類の損切りを足す。
  per   : 1つのバスケットの含み損が SL 円に達したら、そのバスケットだけ決済(足の高値・安値で判定し、その水準で約定)
  total : 口座全体の含み損が SL 円に達したら、全バスケットを決済(足の終値で判定)
損切りしたバスケットは、損切りしなかった場合を単独で先まで再現し(ナンピン・利確のルールどおり、証拠金は無視)、
「利確まで戻ったか」「戻るまでの最大含み損」を記録する。
使い方: python3 sl_study.py M1.csv
"""
import copy
import sys

import pandas as pd

import backtest_ragnarok_abc_v2 as bt


class SLEngine(bt.Engine):
    def __init__(self, m1, sl_yen=None, sl_mode="per", **kw):
        super().__init__(m1, **kw)
        self.sl_yen = sl_yen
        self.sl_mode = sl_mode
        self.sl_events = []          # (損切り時刻, バスケットのコピー, 損切り額)

    def _sl_bid(self, b):
        """含み損がちょうど −SL円 になるbid"""
        d = self.sl_yen / (b.total_lots * bt.YEN_PER_DOLLAR_LOT)
        return b.avg_price - d if b.direction == 1 else b.avg_price + d - bt.SPREAD

    def account(self, t, bar):
        if self.sl_yen:
            if self.sl_mode == "per":
                for key, b in list(self.baskets.items()):
                    lvl = self._sl_bid(b)
                    hit = bar["low"] <= lvl if b.direction == 1 else bar["high"] >= lvl
                    if hit:
                        fill = min(lvl, bar["open"]) if b.direction == 1 else max(lvl, bar["open"])
                        r = b.result(t, fill, "sl")
                        self.closed.append(r)
                        self.sl_events.append((t, copy.deepcopy(b), r["profit_yen"]))
                        if self.balance is not None:
                            self.balance += r["profit_yen"]
                        del self.baskets[key]
            else:
                total = sum(b.floating_yen(bar["close"]) for b in self.baskets.values())
                if total <= -self.sl_yen:
                    for key, b in list(self.baskets.items()):
                        r = b.result(t, bar["close"], "sl")
                        self.closed.append(r)
                        self.sl_events.append((t, copy.deepcopy(b), r["profit_yen"]))
                        if self.balance is not None:
                            self.balance += r["profit_yen"]
                        del self.baskets[key]
        super().account(t, bar)


def forward(m1, t0, b, max_legs):
    """損切りしなかった場合: バスケット単独でルールどおりに先まで進める"""
    b = copy.deepcopy(b)
    worst = b.floating_yen(m1.loc[t0, "close"])
    eng = bt.Engine(m1.iloc[:1], max_legs=max_legs)      # nanpins() を使うための入れ物
    eng.baskets = {("x", b.direction): b}
    for t, bar in m1.loc[t0:].iloc[1:].iterrows():
        level = b.tp_bid()
        if (bar["high"] >= level) if b.direction == 1 else (bar["low"] <= level):
            return dict(recovered=True, worst=worst, legs=b.legs, lots=b.total_lots, hours=(t - t0).total_seconds() / 3600)
        eng.nanpins(t, bar)
        worst = min(worst, b.floating_yen(bar["low"] if b.direction == 1 else bar["high"]))
    return dict(recovered=False, worst=worst, legs=b.legs, lots=b.total_lots, hours=None)


def run(m1, sl, mode, fire, seed, equity=180901, max_legs=40):
    eng = SLEngine(m1, sl_yen=sl, sl_mode=mode, fire=fire, seed=seed, equity=equity, max_legs=max_legs)
    closed, still_open = eng.run()
    tp = closed[closed.reason == "tp"] if len(closed) else closed
    sls = closed[closed.reason == "sl"] if len(closed) else closed
    fw = [forward(m1, t, b, max_legs) for t, b, _ in eng.sl_events]
    rec = [f for f in fw if f["recovered"]]
    return dict(sl=sl or 0, mode=mode, fire=f"{fire}{seed}",
                stopout=eng.stats["stopout"][0] if eng.stats["stopout"] else None,
                balance=round(eng.balance), tp_yen=round(tp.profit_yen.sum()) if len(tp) else 0,
                sl_n=len(sls), sl_yen=round(sls.profit_yen.sum()) if len(sls) else 0,
                rec_n=len(rec), rec_worst=min((f["worst"] for f in rec), default=0),
                rec_worst_med=pd.Series([f["worst"] for f in rec]).median() if rec else 0,
                norec_worst=min((f["worst"] for f in fw if not f["recovered"]), default=0))


if __name__ == "__main__":
    m1 = bt.load_m1(sys.argv[1])
    rows = []
    for mode in ("per", "total"):
        for sl in (None, 10000, 20000, 30000, 50000, 70000, 100000, 150000):
            if mode == "total" and sl is None:
                continue
            for fire, seed in (("always", 0), ("prob", 0), ("prob", 1), ("prob", 2), ("prob", 3), ("prob", 4)):
                r = run(m1, sl, mode, fire, seed)
                rows.append(r)
                print(r, flush=True)
    pd.DataFrame(rows).to_csv("sl_study_result.csv", index=False)
