"""解析39: RSI をボリンジャーバンド(RSI の m 本平均 ± k σ)で見た入口を、解析38のエンジン(tf_sl.engine)で検証する。
入口の型(M15 の確定足で判定、発注は次の足の始値):
 rev   : 上昇トレンド(終値>EMA200)で RSI がバンド下限を割った足 → 買い(売りは逆)  ※押し目。RSI2<10 の代わりに「バンド」で測る
 recross: RSI が下限を割った後、下限の内側に戻った足 → 買い(売りは逆)           ※底打ちの確認を待つ
 brk   : RSI が上限を上抜けた足 → 順張りの買い(下限を下抜けで売り)             ※モメンタム
トレンド: 終値と EMA200 の位置。フィルター: なし / h1h4 / h4adx(tf_model と同じ)。
"""
import sys, itertools, numpy as np, pandas as pd
import tf_model as t, tf_sl as sl, tf_m5 as m5

def rsi_bb(d, n, m, k):
    r = pd.Series(d.o.C.values, index=d.o.index)
    rs = t.rsi(r, n); mid = rs.rolling(m).mean(); sd = rs.rolling(m).std(ddof=0)
    return rs.values, (mid + k * sd).values, (mid - k * sd).values

def sig(d, typ, n, m, k):
    rs, up, lo = rsi_bb(d, n, m, k); C = d.C; P = lambda a: np.r_[np.nan, a[:-1]]
    s = np.zeros(d.N, int); tu = C > d.e200; td = C < d.e200
    if typ == 'rev':
        s[tu & (rs < lo)] = 1; s[td & (rs > up)] = -1
    elif typ == 'recross':
        s[tu & (P(rs) < P(lo)) & (rs >= lo)] = 1; s[td & (P(rs) > P(up)) & (rs <= up)] = -1
    elif typ == 'brk':
        s[tu & (rs > up) & (P(rs) <= P(up))] = 1; s[td & (rs < lo) & (P(rs) >= P(lo))] = -1
    s[:300] = 0
    return s

CFGS = {   # (nl,nstep,nmult,pl,pstep,pmult,tp,frac,trail,sl,slip)
 'R型(ピラ2,tp0.5,損切5)': (0, 1, 1, 2, 1.0, 1.0, 0.5, 0.3, 4, 5.0, 0.1),
 'ピラ無し(tp0.5,損切5)':   (0, 1, 1, 0, 1.0, 1.0, 0.5, 0.3, 4, 5.0, 0.1),
 'ピラ2,tp0.3,損切5':      (0, 1, 1, 2, 1.0, 1.0, 0.3, 0.3, 4, 5.0, 0.1),
 'ピラ2,tp0.5,損切3':      (0, 1, 1, 2, 1.0, 1.0, 0.5, 0.3, 4, 3.0, 0.1),
 'ピラ2,tp0.5,損切8':      (0, 1, 1, 2, 1.0, 1.0, 0.5, 0.3, 4, 8.0, 0.1),
 'ピラ無し,tp0.75,損切4':  (0, 1, 1, 0, 1.0, 1.0, 0.75, 0.3, 4, 4.0, 0.1),
}
if __name__ == '__main__':
    o = t.load_m15(); d = t.Data(o); DAYS = len(set(o.index.date))
    P5 = ['2024-07-23', '2025-01-01', '2025-07-01', '2026-01-01', '2026-05-01', '2026-09-22']
    IDX = [int(np.searchsorted(o.index.values, np.datetime64(x))) for x in P5]; IDX[0] = 200
    SEG = list(zip(IDX[:-1], IDX[1:])); HALF = int(np.searchsorted(o.index.values, np.datetime64('2026-01-01')))
    rows = []
    for typ, n, k, flt in itertools.product(['rev', 'recross', 'brk'], [2, 9, 14], [1.5, 2.0, 2.5], ['none', 'h1h4', 'h4adx']):
        s = t.apply_filter(d, sig(d, typ, n, 20, k), flt); ev = sl.make_events(d, s)
        for cn, cfg in CFGS.items():
            r = sl.engine(d.O, d.H, d.L, d.C, ev, cfg, i0=200)
            a = sl.summarize(r, 200, d.N, SEG, DAYS)
            b1 = sl.summarize(r, 200, HALF, [(200, HALF)], len(set(o.index.date[200:HALF])))
            b2 = sl.summarize(r, HALF, d.N, [(HALF, d.N)], len(set(o.index.date[HALF:])))
            rows.append(dict(typ=typ, n=n, k=k, flt=flt, cfg=cn, N=a['n'], win=a['win'], pf=a['pf'], pnl=a['pnl'], dd=a['dd'], worst=a['worst'],
                             epd=a['epd'], pf_is=b1['pf'], pf_oos=b2['pf'], pos5=sum(1 for x in a['seg_pnl'] if x > 0), seg=[round(x) for x in a['seg_pnl']]))
    df = pd.DataFrame(rows); df.to_csv('tf_rsibb.csv', index=False)
    print('全', len(df), '通り')
    print('--- 型別: 取引100以上の PF 中央値 / 前後とも PF>1 の割合 / 5期間すべてプラスの数')
    g = df[df.N >= 100]
    for typ, x in g.groupby('typ'):
        print(typ, len(x), '通り PF中央値', round(x.pf.median(), 2), '前後PF>1', round(100 * ((x.pf_is > 1) & (x.pf_oos > 1)).mean()), '% 5期間プラス', int((x.pos5 == 5).sum()))
    ok = df[(df.N >= 300) & (df.pf_is > 1) & (df.pf_oos > 1) & (df.pos5 == 5) & (df.win >= 70)].sort_values('pf', ascending=False)
    print('--- 取引300以上・勝率70%以上・前後PF>1・5期間すべてプラス:', len(ok), '通り。上位20')
    print(ok.head(20).to_string())
    print('--- 参考: 解析38の R(RSI2<10 固定しきい値)')
    s = t.apply_filter(d, t.signals(d, 'rsi2'), 'h4adx'); ev = sl.make_events(d, s)
    r = sl.engine(d.O, d.H, d.L, d.C, ev, CFGS['R型(ピラ2,tp0.5,損切5)'], i0=200); a = sl.summarize(r, 200, d.N, SEG, DAYS)
    print({k_: (round(v, 2) if isinstance(v, float) else v) for k_, v in a.items() if k_ in ('n', 'win', 'pf', 'pnl', 'dd', 'worst', 'epd', 'seg_pnl')})
