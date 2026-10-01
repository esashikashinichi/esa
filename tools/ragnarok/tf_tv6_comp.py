import numpy as np, tf_model as t, tf_sl4 as sl, tf_tv as v, tf_tv3 as w, tf_tv6 as z
d=v.d; N=v.N; E0=10000.0; YEN=t.YEN
C=lambda cn:w.CFC[cn]
CANDS=[('Ichi TK+雲 × MMT Fixed%(1.0) flip(フィルターなし・ナンピン2)','Ichi TK+雲',('MMT Fixed%(1.0) flip',),'none','ナンピン2'),
 ('HalfTrend(2,2) × MMT Fixed%(1.0) zone(H4+ADX・ナンピン2+ピラ2 利確0.3)','HalfTrend(2,2)',('MMT Fixed%(1.0) zone',),'h4adx','ナンピン2+ピラ2 利確0.3'),
 ('DIクロス × MMT Fixed%(1.0) zone × VixFix(H4+ADX・ナンピン2)','DIクロス',('MMT Fixed%(1.0) zone','VixFix(22)'),'h4adx','ナンピン2'),
 ('DIクロス × MMT Fixed%(1.0) flip × VixFix(H4+ADX・ナンピン2)','DIクロス',('MMT Fixed%(1.0) flip','VixFix(22)'),'h4adx','ナンピン2'),
 ('(参考)DIクロス+H4 ナンピン2','DIクロス',(),'h4','ナンピン2')]
def stat(r):
    eqc=E0+r['eqc'][200:]*YEN; eqa=E0+r['eqa'][200:]*YEN; pk=np.maximum.accumulate(eqc); return eqc[-1],((pk-eqa)/pk).max()*100
print('=====',v.TF)
for name,A,Bs,f,cn in CANDS:
    s=z.combo(A,Bs); s=t.apply_filter(d,s,f) if f!='none' else s; cfg,sl0=C(cn); ev=sl.make_events(d,s,None,sl0); out=[]
    for K in (3000,2000,1000):
        row=[]
        for spr in (None,t.SPR*2):
            r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,comp=(E0,K,30),spr=spr); fz,dd=stat(r); row.append(f'{fz:,.0f}円(DD{dd:.0f}%)')
        out.append(f'K={K}: {row[0]} / スプレッド2倍 {row[1]}')
    print('==',name); [print('   ',x) for x in out]
