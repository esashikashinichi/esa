"""解析43: 資金を最短で増やす組み合わせ。入口の組み合わせ(複数の入口の和集合)× ピラミッディングの形 × 複利 K。
目標 = 1万円 → 3万円。指標: 3倍までの日数(始点を毎月ずらした中央値)、最大の落ち込み(スプレッド等倍・2倍)、最終残高。"""
import itertools, numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl4 as sl, tf_pyr as p, tf_comp as c
d=p.d; o=p.o; idx=o.index; E0=10000.0; YEN=t.YEN
SIG={k:p.entry(k) for k in ('R','rc2','EMA','rc14')}
def union(names):
    s=np.zeros(d.N,int)
    for n in names:
        s=np.where(s!=0,s,SIG[n])
    return s
SETS={'R':['R'],'R+rc2':['R','rc2'],'R+EMA':['R','EMA'],'R+rc2+EMA':['R','rc2','EMA'],'R+rc14':['R','rc14']}
EVS={k:sl.make_events(d,union(v)) for k,v in SETS.items()}
CF={'基準':p.cfg(2,1.0,1.0,0.5,0.3,4,0,0),'×1.5':p.cfg(2,1.0,1.5,0.5,0.3,4,0,0),'×1.5 利確0.3':p.cfg(2,1.0,1.5,0.3,0.3,4,0,0),
    '利確後も買増4':p.cfg(4,1.0,1.0,0.5,0.3,4,0,1),'×1.5+利確後も買増4':p.cfg(4,1.0,1.5,0.5,0.3,4,0,1)}
def days_to(eq,i0,target):
    h=np.nonzero(eq>=target)[0]
    return (idx[i0+h[0]]-idx[i0]).days if len(h) else np.nan
def one(a):
    ent,cn,K,mm,i0,spr=a; r=sl.engine(d.O,d.H,d.L,d.C,EVS[ent],CF[cn],i0=i0,comp=(E0,K,mm),spr=spr)
    eqc,eqa,dd=c.curve(r,i0,d.N); yrs=(idx[-1]-idx[i0]).days/365.25
    return dict(ent=ent,cfg=cn,K=K,mm=mm,i0=i0,spr=spr is not None,final=eqc[-1],dd=dd,minE=eqa.min(),d3=days_to(eqc,i0,3*E0),d5=days_to(eqc,i0,5*E0),N=r['entries'],yrs=yrs)
if __name__=='__main__':
    Ks=[750,1000,1500,2000,3000]
    A=[(e,cn,K,30,200,s) for e in SETS for cn in CF for K in Ks for s in (None,t.SPR*2)]
    with Pool() as pl: R=pl.map(one,A,chunksize=4)
    x=pd.DataFrame(R); a=x[~x.spr].drop(columns='spr'); b=x[x.spr][['ent','cfg','K','final','dd','minE','d3']].rename(columns={'final':'final2','dd':'dd2','minE':'minE2','d3':'d3_2'})
    m=a.merge(b,on=['ent','cfg','K']); m.to_csv('tf_fast1.csv',index=False)
    pd.set_option('display.width',250); print('全',len(m))
    ok=m[(m.dd<=45)&(m.dd2<=55)].sort_values('d3'); print('--- DD≤45%(等倍)かつ DD≤55%(スプレッド2倍)で、3倍までの日数が短い順 上位15'); print(ok.head(15)[['ent','cfg','K','N','final','dd','d3','d5','final2','dd2','d3_2','minE']].round(0).to_string())
    print('--- 制約なしで 3倍までが最短 上位8'); print(m.sort_values('d3').head(8)[['ent','cfg','K','final','dd','d3','final2','dd2']].round(0).to_string())
    ok.head(12).to_csv('tf_fast_top.csv',index=False)
