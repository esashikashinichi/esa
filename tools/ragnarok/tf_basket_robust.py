"""解析37: 候補の頑健さ(5期間・周辺の設定・スプレッド2倍・M1 足での答え合わせ)"""
import tf_model as t, tf_basket as b, numpy as np, pandas as pd
o=t.load_m15(); d=t.Data(o)
a=pd.read_csv('../data/M1_long.csv',header=None,names=['D','T','O','H','L','C','V'])
a['t']=pd.to_datetime(a['D']+' '+a['T'],format='%Y.%m.%d %H:%M'); m=a.drop_duplicates('t').set_index('t').sort_index()
fine=(m.O.values,m.H.values,m.L.values,m.C.values,m.index.values)
I0=int(np.searchsorted(o.index.values,np.datetime64('2026-07-18')))
P=[np.datetime64(x) for x in ('2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01','2026-09-22')]
IDX=[int(np.searchsorted(o.index.values,x)) for x in P]
CANDS={
 'P1 RSI2押し目+H4+ADX・ピラミッド':('rsi2','h4adx',dict(mode='pyr',step=1.0,maxlegs=3,mult=1.5,sl=6,tp=0.5,trail=4,frac=0.3)),
 'P2 EMA20押し目+H1・H4・ピラミッド':('pb_ema','h1h4',dict(mode='pyr',step=1.0,maxlegs=3,mult=1.5,sl=6,tp=0.5,trail=4,frac=0.3)),
 'N1 EMA20押し目+H1・H4・ナンピン':('pb_ema','h1h4',dict(mode='nan',step=2.0,maxlegs=3,mult=1.5,sl=5,tp=0.5,trail=4,frac=0.3)),
 'N2 RSI2押し目+H4+ADX・ナンピン':('rsi2','h4adx',dict(mode='nan',step=1.0,maxlegs=4,mult=1.5,sl=8,tp=0.5,trail=4,frac=0.3)),
}
BASE={'基準 EMA20押し目(1段)':('pb_ema','h1h4',dict(mode='nan',step=1.0,maxlegs=1,mult=1.0,sl=4,tp=0.75,trail=4,frac=0.3)),
      '基準 RSI2押し目(1段)':('rsi2','h4adx',dict(mode='nan',step=1.0,maxlegs=1,mult=1.0,sl=5,tp=0.5,trail=4,frac=0.3))}
if __name__=='__main__':
    for name,(e,f,kw) in {**BASE,**CANDS}.items():
        s=t.apply_filter(d,t.signals(d,e),f); full=b.stats(b.sim(d,s,**kw)); print('=====',name,kw); print('全期間',full)
        pr=[b.stats(b.sim(d,s,i0=x,i1=y,**kw)) for x,y in zip(IDX[:-1],IDX[1:])]
        print('  5期間 PF:',[x['pf'] for x in pr],' 勝率:',[x['win'] for x in pr],' 損益:',[x['total'] for x in pr])
        nb=[]
        for k_,vals in dict(step=[0.5,0.75,1.0,1.5,2.0],maxlegs=[2,3,4,5],mult=[1.0,1.5],sl=[4,5,6,8],tp=[0.5,0.75,1.0],frac=[0.3,0.5]).items():
            if kw['maxlegs']==1 and k_ in ('step','maxlegs','mult'): continue
            for v in vals:
                kk=dict(kw); kk[k_]=v; r=b.stats(b.sim(d,s,**kk)); nb.append((k_,v,r['win'],r['pf'],r['dd']))
        if nb: print('  周辺(1つずつ変更) 勝率の最小',min(x[2] for x in nb),' PFの最小',min(x[3] for x in nb),' 落ち込みの最悪',min(x[4] for x in nb))
        old=t.SPR; t.SPR=old*2; r2=b.stats(b.sim(d,s,**kw)); t.SPR=old; print('  スプレッド2倍:',r2)
        A=b.stats(b.sim(d,s,i0=I0,**kw)); B=b.stats(b.sim(d,s,i0=I0,fine=fine,**kw)); print('  M15計算(07-18〜):',A); print('  M1 計算(07-18〜):',B)
        yrs=(o.index[-1]-o.index[200]).days/365.25
        for lot in (0.01,0.02,0.03):
            mu=lot/0.01; print(f'   {lot}ロット: 年 {round(full["total"]*mu/yrs):,}円 最大の落ち込み {round(full["dd"]*mu):,}円 1回の最大損 {round(full["worst"]*t.YEN*mu):,}円 最大ロット {round(full["maxlot"]*lot,2)}')
