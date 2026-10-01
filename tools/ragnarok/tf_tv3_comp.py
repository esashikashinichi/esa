import numpy as np, pandas as pd, tf_model as t, tf_sl4 as sl, tf_tv as v, tf_tv3 as w
d=v.d; N=v.N; E0=10000.0; YEN=t.YEN
for n in w.IND: w.raw(n)
CANDS=[('ST(10,3)+H4 ナンピン2(幅0.5・×1.5・損切り15)+ピラ2 利確0.3',lambda:t.apply_filter(d,w.raw('ST(10,3)'),'h4'),(2,0.5,1.5,2,1.0,1.0,0.3,0.3,4,15.0,0.1,0,0),15.0),
 ('ST(10,3)+H4 ナンピン2(幅1.0・×1.5・損切り15)+ピラ2 利確0.5',lambda:t.apply_filter(d,w.raw('ST(10,3)'),'h4'),(2,1.0,1.5,2,1.0,1.0,0.5,0.3,4,15.0,0.1,0,0),15.0),
 ('DIクロス+UT(1,10)+H4ADX ナンピン2+ピラ2 利確0.3',lambda:t.apply_filter(d,w.combo('DIクロス',('UT(1,10)',)),'h4adx'),v.CF['ナンピン2+ピラ2 利確0.3'][0],8.0),
 ('DIクロス+H4 ナンピン2(幅1.0・×1.5・損切り8)',lambda:t.apply_filter(d,w.raw('DIクロス'),'h4'),v.CF['ナンピン2'][0],8.0),
 ('R ピラ2(参考)',lambda:t.apply_filter(d,t.signals(d,'rsi2'),'h4adx'),v.CF['ピラ2'][0],5.0)]
def stat(r):
    eqc=E0+r['eqc'][200:]*YEN; eqa=E0+r['eqa'][200:]*YEN; pk=np.maximum.accumulate(eqc); return eqc[-1],((pk-eqa)/pk).max()*100
print('=====',v.TF)
for name,fn,cfg,sl0 in CANDS:
    s=fn(); ev=sl.make_events(d,s,None,sl0); line=[]
    for K in (3000,2000,1000):
        row=[]
        for spr in (None,t.SPR*2):
            r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,comp=(E0,K,30),spr=spr); f,dd=stat(r); row.append(f'{f:,.0f}円(DD{dd:.0f}%)')
        line.append(f'K={K}: {row[0]} / スプレッド2倍 {row[1]}')
    print('==',name); [print('   ',x) for x in line]
