"""解析51: これまでの上位候補を同じルールで比較。各候補で「ロールング始点9通りの最大の落ち込み(等倍)<=45%、スプレッド2倍で<=55%」を満たす最小の K(最も強い複利)を選び、
3倍(1万円→3万円)までの日数・最終残高・M5 確認を並べる。M15(2.2年)。"""
import numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl4 as sl, tf_tv as v, tf_tv3 as w, tf_tv4 as x4, tf_tv5 as x5, tf_pyr as p, tf_macd as mc, tf_rsibb as rb, tf_mtf as mt, tf_m5 as m5, tf_tv6 as x6
d=v.d; idx=v.idx; N=v.N; E0=10000.0; YEN=t.YEN
U=lambda a,b:np.where(a!=0,a,b)
R=t.apply_filter(d,t.signals(d,'rsi2'),'h4adx'); PB=mc.filt(mc.entry('pb2'),'h4'); RC14=rb.sig(d,'recross',14,20,1.5); RC2=rb.sig(d,'recross',2,20,2.0)
DI=w.raw('DIクロス'); ST=w.raw('ST(10,3)')
def cmb(A,Bs,f): s=x6.combo(A,Bs); return t.apply_filter(d,s,f) if f!='none' else s
cfgs={'pyr2':(0,1,1,2,1.0,1.0,0.5,0.3,4,5.0,0.1,0,0),'pyr2tp3':(0,1,1,2,1.0,1.0,0.3,0.3,4,5.0,0.1,0,0),'x15tp3':(0,1,1,2,1.0,1.5,0.3,0.3,4,5.0,0.1,0,0),'x15':(0,1,1,2,1.0,1.5,0.5,0.3,4,5.0,0.1,0,0),
 'nan2':(2,1,1.5,0,1.0,1.0,0.5,0.3,4,8.0,0.1,0,0),'nan2pyr2':(2,1,1.5,2,1.0,1.0,0.3,0.3,4,8.0,0.1,0,0)}
C={'R + ピラミッディング2段(利確0.5)':(R,'pyr2',5.0),'R + ピラミッディング2段(利確0.3)':(R,'pyr2tp3',5.0),'R + ピラミッディング ×1.5(利確0.3)':(R,'x15tp3',5.0),
 'R または MACD押し(pb2+H4)(利確0.3)':(U(R,PB),'pyr2tp3',5.0),'R または MACD押し(利確0.5)':(U(R,PB),'pyr2',5.0),
 'R または recross RSI14 ×1.5(利確0.3)':(U(R,RC14),'x15tp3',5.0),'R または recross RSI2 ×1.5(利確0.3)':(U(R,RC2),'x15tp3',5.0),
 'DIクロス+H4 ナンピン2段':(t.apply_filter(d,DI,'h4'),'nan2',8.0),'DIクロス+H4 ナンピン2+ピラ2(利確0.3)':(t.apply_filter(d,DI,'h4'),'nan2pyr2',8.0),
 'Supertrend(10,3)+H4 ナンピン2(幅0.5・×1.5・損切15)+ピラ2':(t.apply_filter(d,ST,'h4'),(2,0.5,1.5,2,1.0,1.0,0.3,0.3,4,15.0,0.1,0,0),15.0),
 'Supertrend(10,3)+H4 ナンピン2(幅1.0・×1.5・損切15)+ピラ2(利確0.5)':(t.apply_filter(d,ST,'h4'),(2,1.0,1.5,2,1.0,1.0,0.5,0.3,4,15.0,0.1,0,0),15.0),
 'DIクロス×MMT Fixed%zone×VixFix(H4+ADX)ナンピン2':(cmb('DIクロス',('MMT Fixed%(1.0) zone','VixFix(22)'),'h4adx'),'nan2',8.0),
 'DIクロス×MMT Fixed%flip×VixFix(H4+ADX)ナンピン2':(cmb('DIクロス',('MMT Fixed%(1.0) flip','VixFix(22)'),'h4adx'),'nan2',8.0),
 'HalfTrend(2,2)×MMT Fixed%zone(H4+ADX)ナンピン2+ピラ2':(cmb('HalfTrend(2,2)',('MMT Fixed%(1.0) zone',),'h4adx'),'nan2pyr2',8.0),
 'Ichimoku TK+雲×MMT Fixed%flip ナンピン2':(cmb('Ichi TK+雲',('MMT Fixed%(1.0) flip',),'none'),'nan2',8.0),
 'MMT Chandelier(22,14,2)zone(H1H4)ナンピン2+ピラ2':(t.apply_filter(d,x5.SIGS['Chandelier(22,14,2) zone'],'h1h4'),'nan2pyr2',8.0),
 'DIクロス MTF(H1 EMA+DI)ナンピン2+ピラ2':(mt.mtf(DI,'mEMA+mDI'),'nan2pyr2',8.0),'DIクロス MTF(H1 EMA)ナンピン2+ピラ2':(mt.mtf(DI,'mEMA'),'nan2pyr2',8.0),
 'Donchian55+H1H4 ピラ2(参考)':(t.apply_filter(d,t.signals(d,'don55'),'h1h4'),'pyr2',5.0),
 'Nadaraya-Watson(H1 DI)ナンピン2+ピラ2':(mt.mtf(w.raw('Nadaraya-Watson(8,3)') if 'Nadaraya-Watson(8,3)' in v.SIG else mt.get('Nadaraya-Watson(8,3)'),'mDI'),'nan2pyr2',8.0)}
def cf(c): return cfgs[c] if isinstance(c,str) else c
STARTS=[int(np.searchsorted(idx.values,np.datetime64(x+'-01'))) for x in ('2024-08','2024-11','2025-02','2025-05','2025-08','2025-11','2026-01','2026-03','2026-05')]
KS=[750,1000,1500,2000,3000,5000]
EVC={}
def ev(name):
    if name not in EVC: s,c,sl0=C[name]; EVC[name]=sl.make_events(d,s,None,sl0)
    return EVC[name]
def days_to(eq,i0,tg): h=np.nonzero(eq>=tg)[0]; return (idx[i0+h[0]]-idx[i0]).days if len(h) else np.inf
def one(a):
    name,K,i0,spr=a; s,c,sl0=C[name]; r=sl.engine(d.O,d.H,d.L,d.C,ev(name),cf(c),i0=i0,comp=(E0,K,30),spr=spr)
    eqc=E0+r['eqc'][i0:]*YEN; eqa=E0+r['eqa'][i0:]*YEN; pk=np.maximum.accumulate(eqc)
    return dict(name=name,K=K,i0=i0,spr=spr is not None,final=eqc[-1],dd=((pk-eqa)/pk).max()*100,d3=days_to(eqc,i0,3*E0),ent=r['entries'])
if __name__=='__main__':
    A=[(n,K,i0,s) for n in C for K in KS for i0 in STARTS for s in (None,t.SPR*2)]
    for n in C: ev(n)
    with Pool() as pl: rows=pl.map(one,A,chunksize=8)
    x=pd.DataFrame(rows); x.to_csv('tf_rank_raw.csv',index=False)
    g=x.groupby(['name','K','spr']).agg(dd=('dd','max'),d3=('d3','median'),reach=('d3',lambda s:int(np.isfinite(s).sum())),fmin=('final','min'),fmed=('final','median')).reset_index()
    a=g[~g.spr].drop(columns='spr'); b=g[g.spr].drop(columns='spr').rename(columns={'dd':'dd2','d3':'d3_2','reach':'reach2','fmin':'fmin2','fmed':'fmed2'})
    m=a.merge(b,on=['name','K']); m.to_csv('tf_rank_K.csv',index=False); print('done',len(m))
