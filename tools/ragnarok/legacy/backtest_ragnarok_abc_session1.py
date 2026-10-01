"""
ラグナロク(Ragnarok EA) a/b/c 独立グリッド構造 再現コード
============================================================

【確定事項(実データで検証済み)】
  1. a/b/c は独立した3つのナンピングリッド。
     各グリッドは「買い側バスケット」「売り側バスケット」を
     "同時に・独立に" 保有できる(例: bグリッドが売りナンピン中でも、
     別途bグリッドの買いバスケットが新規に立ち上がる)。
  2. 初弾(新規バスケット開始)ルール:
       現在値 - 3分前に確定した1分足の終値 > 0 → 買い
       現在値 - 3分前に確定した1分足の終値 < 0 → 売り
     b/c双方、買い/売り双方で4/4検証済み。
  3. ナンピン倍率: 直前レグロット × 1.5
     (ea_monitor.csv の lot_multiplier 列で実測、0.10→0.15→0.23→0.34 等)
  4. 利確(バスケット一括決済): 加重平均建値から含み益方向へ
     約130〜146pips(実測3件平均、cグリッド138pips/bグリッド131.6pips/
     aグリッド145.8pips)離れたら全レグ一括決済。TARGET_PIPS=140を採用。

【未確定事項(このコードでは未実装 or 仮置き)】
  - ナンピンの正確なタイミング条件
    (「最短7分1秒間隔+急騰急落中はスキップ」という仮説はあるが未確定)
  - a/b/cそれぞれの初弾がなぜ"同時"ではなく数分〜数十分ずれて
    発生するのか(3つが完全に同一ルールなら同時発火するはずだが、
    実際はズレている → 未特定の差別化要因がある)
  - grid_step_ptsフィールドの算出ロジック
  - 利確pips幅がレグ数/状況で変動するか(単一レグ即決済ケースは
    約70pipsで140pipsより明らかに小さかった)

このコードは「確定事項」だけを反映したa/b/c 3系統・双方向バスケットの
近似モデルです。ナンピンタイミングは暫定的に旧仮説(3分モメンタムの
エッジ検知)を流用していますが、実測とのズレが残っている点に注意してください。
"""
import pandas as pd
import numpy as np

POINT = 0.01
BASE_LOT = 0.10
LOT_MULT = 1.5
TARGET_PIPS = 140       # 加重平均建値からの利確幅(実測131.6〜145.8pipsの中心値)
MAX_LEGS = 40            # 実機のNanpinCount=40(起動ログで確認)に合わせる
SLOT_NAMES = ["a", "b", "c"]

M1_PATH = "/root/.claude/uploads/287721a5-5846-58b3-9fd8-a0d890a1883f/99b6befb-GOLDmicro1.csv"


def load_m1():
    df = pd.read_csv(M1_PATH, header=None, names=["date", "time", "open", "high", "low", "close", "volume"])
    df["dt"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M")
    df = df.sort_values("dt").reset_index(drop=True)
    return df


class Basket:
    """1グリッド・1方向ぶんのナンピンバスケット"""
    def __init__(self, direction, price):
        self.direction = direction          # +1=買い, -1=売り
        self.legs_price = [price]
        self.legs_lot = [BASE_LOT]
        self.last_leg_lot = BASE_LOT
        self.worst_pips = 0.0

    @property
    def avg_price(self):
        return np.average(self.legs_price, weights=self.legs_lot)

    @property
    def total_lots(self):
        return sum(self.legs_lot)

    def profit_pips(self, price):
        if self.direction == 1:
            return (price - self.avg_price) / POINT
        return (self.avg_price - price) / POINT

    def add_leg(self, price):
        new_lot = round(self.last_leg_lot * LOT_MULT, 2)
        self.legs_price.append(price)
        self.legs_lot.append(new_lot)
        self.last_leg_lot = new_lot


class GridSlot:
    """a/b/cいずれか1系統。買い・売りバスケットを独立に持てる"""
    def __init__(self, name):
        self.name = name
        self.baskets = {1: None, -1: None}   # 方向ごとに最大1バスケット
        # ナンピン用エッジ検知の内部状態(方向ごと)
        self._prev_opposite = {1: False, -1: False}

    def step(self, price, mom_sign, i, trades, stuck):
        for direction in (1, -1):
            b = self.baskets[direction]

            # --- 初弾判定(このグリッドのこの方向にバスケットが無ければ) ---
            if b is None:
                if mom_sign == direction:
                    self.baskets[direction] = Basket(direction, price)
                continue

            # --- 利確判定 ---
            profit = b.profit_pips(price)
            b.worst_pips = min(b.worst_pips, profit)
            if profit >= TARGET_PIPS:
                trades.append(dict(
                    slot=self.name, direction=direction, legs=len(b.legs_price),
                    total_lots=round(b.total_lots, 2), avg_price=b.avg_price,
                    close_price=price, profit_pips=profit, worst_pips=b.worst_pips,
                    close_idx=i,
                ))
                self.baskets[direction] = None
                continue

            # --- ナンピン判定(暫定: モメンタムがバスケット方向と逆に
            #     転じたエッジ。※タイミング条件は未確定、近似モデル) ---
            is_opposite_now = (mom_sign != 0 and mom_sign != direction)
            if is_opposite_now and not self._prev_opposite[direction]:
                if len(b.legs_price) >= MAX_LEGS:
                    stuck.append(dict(
                        slot=self.name, direction=direction, legs=len(b.legs_price),
                        total_lots=round(b.total_lots, 2), avg_price=b.avg_price,
                        close_price=price, profit_pips=profit, worst_pips=b.worst_pips,
                        close_idx=i,
                    ))
                    self.baskets[direction] = None
                else:
                    b.add_leg(price)
            self._prev_opposite[direction] = is_opposite_now


def backtest(df):
    close = df["close"].values
    n = len(close)
    momentum = np.zeros(n)
    momentum[3:] = close[3:] - close[:-3]

    slots = {name: GridSlot(name) for name in SLOT_NAMES}
    trades, stuck = [], []

    for i in range(3, n):
        price = close[i]
        mom = momentum[i]
        mom_sign = 1 if mom > 0 else (-1 if mom < 0 else 0)

        # 注意: a/b/cが実際に「なぜ別々のタイミングで初弾を打つのか」は
        # 未特定。ここでは暫定的に3系統とも同一の判定に従わせているため、
        # 実際のログのような発火タイミングのズレは再現できていない。
        for slot in slots.values():
            slot.step(price, mom_sign, i, trades, stuck)

    return trades, stuck


def summarize(trades, stuck, span_days):
    if not trades:
        print("トレードなし")
    else:
        n = len(trades)
        print(f"バスケット数(決済済): {n}  ({n/span_days:.2f}件/日)")
        for slot in SLOT_NAMES:
            sub = [t for t in trades if t["slot"] == slot]
            print(f"  スロット{slot}: {len(sub)}件")
        legs_dist = pd.Series([t["legs"] for t in trades])
        print(f"平均レグ数: {legs_dist.mean():.2f}  最大レグ数: {legs_dist.max()}")

        YEN_PER_PIP_PER_LOT = 1.576
        total_yen = sum(t["profit_pips"] * t["total_lots"] * YEN_PER_PIP_PER_LOT for t in trades)
        print(f"概算合計損益(決済分のみ): {total_yen:.0f}円")

    print(f"座礁バスケット(MAX_LEGS={MAX_LEGS}到達): {len(stuck)}件")


def main():
    df = load_m1()
    span_days = (df["dt"].iloc[-1] - df["dt"].iloc[0]).total_seconds() / 86400
    print(f"M1データ期間: {df['dt'].iloc[0]} 〜 {df['dt'].iloc[-1]} ({span_days:.1f}日)")
    trades, stuck = backtest(df)
    summarize(trades, stuck, span_days)


if __name__ == "__main__":
    main()
