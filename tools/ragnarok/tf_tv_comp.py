"""解析45 第2段: TradingView 系の上位候補に複利(K=1000/2000/3000)を掛ける。M15(2.2年)と M5(約5か月)、スプレッド等倍・2倍。R(参考)は同じ足でネイティブに作った R。"""
import numpy as np, pandas as pd, tf_model as t, tf_sl4 as sl, tf_tv as v
d=v.d; o=v.o; idx=v.idx; N=v.N; YEN=t.YEN; E0=10000.0
SIGS={'DIクロス+H4':(lambda:t.apply_filter(d,v.dicross(),'h4'),'ナンピン2'),'DIクロス+H4':(lambda:t.apply_filter(d,v.dicross(),'h4'),'ナンピン2'),
}
CANDS=[('DIクロス+H4 ナンピン2',lambda:t.apply_filter(d,v.dicross(),'h4'),'ナンピン2'),
 ('DIクロス+H4 ナンピン2+ピラ2 利確0.3',lambda:t.apply_filter(d,v.dicross(),'h4'),'ナンピン2+ピラ2 利確0.3'),
 ('DIクロス+H4 ピラ2',lambda:t.apply_filter(d,v.dicross(),'h4'),'ピラ2'),
 ('SQZ勢い0+H4 買増し無し',lambda:t.apply_filter(d,v.squeeze('mom'),'h4'),'買増し無し'),
 ('Donchian55+H1H4 ピラ2(参考)',lambda:t.apply_filter(d,t.signals(d,'don55'),'h1h4'),'ピラ2'),
 ('R(RSI2<10+H4+ADX) ピラ2(参考)',lambda:t.apply_filter(d,t.signals(d,'rsi2'),'h4adx'),'ピラ2')]
def stat(r,i0):
    eqc=E0+r['eqc'][i0:]*YEN; eqa=E0+r['eqa'][i0:]*YEN; pk=np.maximum.accumulate(eqc); return eqc[-1],((pk-eqa)/pk).max()*100,eqa.min()
print('=====',v.TF,f'({(idx[-1]-idx[200]).days}日)')
for name,fn,cn in CANDS:
    s=fn(); cfg,sl0=v.CF[cn]; ev=sl.make_events(d,s,None,sl0)
    r0=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200); x=sl.summarize(r0,200,N,v.SEG,v.DAYS)
    out=[f"固定0.01: n={x['n']} 勝率{x['win']:.1f}% PF{x['pf']:.2f} 損益{x['pnl']:.0f}円 落込{x['dd']:.0f} 最大損{x['worst']:.0f}"]
    for K in (3000,2000,1000):
        row=[]
        for spr in (None,t.SPR*2):
            r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,comp=(E0,K,30),spr=spr); f,dd,mn=stat(r,200); row.append(f'{f:,.0f}円(DD{dd:.0f}%)')
        out.append(f'K={K}: {row[0]} / スプレッド2倍 {row[1]}')
    print('==',name,'/',cn); [print('  ',o_) for o_ in out]
