"""1ロジック(1つの束)で、初弾から何ドルの逆行に耐えられるか(解析24)

- ロット: 0.10 から ×1.5(10段目 3.84)、11段目から ×1.2(実測)。上限40段。
- 逆行が止まらずに続き、一定の間隔(step ドル)ごとにナンピンが入ると仮定。
- 損益: 1ロット×1ドル = 157.6円(09-25 の実決済から逆算)。スプレッド 0.55ドル。
- 証拠金: 1ロット 657円。維持率 20% でロスカット。
- 出力: 含み損が 5万円 / 10万円 に届く逆行幅と、維持率 20% に届く逆行幅(段数)。
"""
import numpy as np

Y, M, SPREAD = 157.6, 657, 0.55
LOTS = [0.10, 0.15, 0.23, 0.34, 0.51, 0.76, 1.14, 1.71, 2.56, 3.84] + [round(3.84 * 1.2 ** i, 2) for i in range(1, 31)]


def tolerance(step, equity):
    out = {}
    for x in np.arange(0, 400, 0.05):
        n = min(int(x // step) + 1, 40)
        lots = LOTS[:n]
        loss = sum(l * (x - i * step) for i, l in enumerate(lots)) * Y + sum(lots) * SPREAD * Y
        for key, thr in (('loss50k', 50000), ('loss100k', 100000)):
            if key not in out and loss >= thr:
                out[key] = (round(x, 1), n)
        if equity - loss <= 0.2 * sum(lots) * M:
            out['stopout'] = (round(x, 1), n)
            return out
    return out


if __name__ == '__main__':
    for eq in [111454, 200000, 300000, 500000, 1000000]:
        print(eq, {s: tolerance(s, eq) for s in [1.1, 2.0, 3.0, 3.8, 5.0]})
