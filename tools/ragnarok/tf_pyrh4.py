"""解析54: R の順行の買い増しを「H4 RSI(14)(確定足)が入口後の最高値から少し下がるまで」続ける。
下がり幅 X(RSI ポイント)= 1/2/3/5/8、最大段数 pl=4/6、幅 1.0/0.7 ATR。基準=2段・ゲート無し。M15 2.2年と M5 5か月(複利 K=1500、スプレッド2倍)。"""
import numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl5 as sl, tf_rank as r, tf_rank_m5 as q
d=r.d; E0=r.E0; YEN=t.YEN; M=q.M
c4=d.o.C.resample('4h',label='right',closed='right').last().dropna(); rs4=t.rsi(c4,14)
G15=rs4.reindex(d.o.index,method='ffill').fillna(50).values
G5=rs4.reindex(M.m.index,method='ffill').fillna(50).values
EV=sl.make_events(d,r.R,None,5.0)
E5=q.ev5('R + ピラミッディング2段(利確0.5)')
def cfg(pl,ps): return (0,1,1,pl,ps,1.0,0.5,0.3,4,5.0,0.1,0,0)
GR=[(2,1.0,None)]+[(pl,ps,x) for pl in (4,6) for ps in (1.0,0.7) for x in (1,2,3,5,8)]
def st(rr,i0): ec=E0+rr['eqc'][i0:]*YEN; ea=E0+rr['eqa'][i0:]*YEN; pk=np.maximum.accumulate(ec); return ec[-1],((pk-ea)/pk).max()*100
def one(a):
    pl,ps,x=a; c=cfg(pl,ps); o={}
    g15=(G15,x) if x is not None else None; g5=(G5,x) if x is not None else None
    r0=sl.engine(d.O,d.H,d.L,d.C,EV,c,i0=200,gate=g15); p=np.array([z[0] for z in r0['trades']])*YEN
    o['pf']=p[p>0].sum()/-p[p<0].sum(); o['pnl']=p.sum(); o['n']=len(p)
    ec=r0['eqc'][200:]*YEN; ea=r0['eqa'][200:]*YEN; o['dd1']=(np.maximum.accumulate(ec)-ea).max()
    for lab,spr in (('',None),('s',t.SPR*2)):
        o['c'+lab],o['d'+lab]=st(sl.engine(d.O,d.H,d.L,d.C,EV,c,i0=200,comp=(E0,1500,30),spr=spr,gate=g15),200)
        o['m'+lab],o['md'+lab]=st(sl.engine(M.O,M.H,M.L,M.C,E5,c,i0=1,comp=(E0,1500,30),spr=spr,gate=g5),1)
    return dict(pl=pl,ps=ps,x=x if x is not None else -1,**{k:round(float(v),1) for k,v in o.items()})
if __name__=='__main__':
    with Pool() as pp: rows=pp.map(one,GR)
    pd.DataFrame(rows).to_csv('tf_pyrh4.csv',index=False); print('done',len(rows))
