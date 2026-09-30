"""Ragnarok 解析30: 利確の仕組みと、本番(マイクロ口座)・デモ(ノーマル口座)の違い

入力(区切り ';'):
  real/events_v37.csv  = 本番 ea_monitor_events_v37.csv (09-25)
  real/events_v38.csv  = 本番 ea_monitor_events_v38.csv (09-28)
  demo/events.csv      = デモ demo_ea_monitor_events_v38.csv (09-28〜09-30)

BASKET_CLOSE 行の mfe_pts(決済前の最大含み益、平均建値から)と close_pts(決済幅)を比べる。
「利益で決済した束の MFE の最小値」= 利確の発動ライン、「MFE − 決済幅」= 発動後の戻り。
"""
import numpy as np
import pandas as pd


def closes(path):
    d = pd.read_csv(path, sep=';')
    return d[d.event == 'BASKET_CLOSE'].copy()


def summary(name, x):
    print('=====', name)
    for label, g in (('1段', x[x.legs == 1]), ('2段以上', x[x.legs >= 2])):
        w = g[g.close_pts > 0].copy()
        w['ret'] = w.mfe_pts - w.close_pts
        print(f'{label}: 利益で決済 {len(w)}/{len(g)}  MFE 最小 {w.mfe_pts.min():.1f}  '
              f'MFE 下位5% {w.mfe_pts.quantile(.05):.1f}  MFE 中央 {w.mfe_pts.median():.1f}  '
              f'決済幅 中央 {w.close_pts.median():.1f}  戻り 中央 {w.ret.median():.1f}  '
              f'最大含み益から決済まで 中央 {w.sec_mfe_to_close.median():.0f}秒')
    one = x[(x.legs == 1) & (x.close_pts > 0)]
    print('1段 MFE の分布', np.histogram(one.mfe_pts, bins=[60, 65, 70, 75, 80, 90, 100, 105, 110, 120, 150, 400])[0].tolist(),
          '(区切り 60,65,70,75,80,90,100,105,110,120,150,400)')


def main():
    real = pd.concat([closes('real/events_v37.csv'), closes('real/events_v38.csv')])
    real = real.drop_duplicates(['time', 'logic', 'side', 'basket'])
    demo = closes('demo/events.csv')
    summary('本番(GOLDmicro 0.1ロット)', real)
    summary('デモ(GOLD 0.01ロット)', demo)
    print('本番 09-28 だけ(デモと同じ時間帯):')
    r28 = real[real.time.str.startswith('2026.09.28') & (real.legs == 1) & (real.close_pts > 0)]
    d28 = demo[demo.time.str.startswith('2026.09.28') & (demo.legs == 1) & (demo.close_pts > 0)]
    print(f'  1段 MFE 最小 本番 {r28.mfe_pts.min():.1f}({len(r28)}束) / デモ {d28.mfe_pts.min():.1f}({len(d28)}束)')
    print('損失の決済(本番):')
    print(real[real.close_pts < 0][['time', 'logic', 'side', 'legs', 'total_lots', 'close_pts', 'profit_yen']].to_string())


if __name__ == '__main__':
    main()
