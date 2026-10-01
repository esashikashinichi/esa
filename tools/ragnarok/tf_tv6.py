"""解析49: RedK MMTStop(各設定)と他の TradingView 系インジケーターとの組み合わせ。トリガー A + 方向確認 B(・C)。TF=M15/M5。"""
import sys, itertools, numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_tv as v, tf_tv3 as w, tf_tv4 as x4, tf_tv5 as x5
d=v.d
MM=['ATR(14,3) flip','Chandelier(22,14,2) flip','Chandelier(22,14,2) zone','Chandelier(22,14,3) zone','Donchian(40) flip','Fixed%(1.0) flip','Fixed%(1.0) zone','StdDev(20,2) flip','ATR(10,3) zone']
OT=['DIクロス','ST(10,3)','SQZ勢い0','SQZ発火','PSAR','Ichi TK+雲','Ichi 雲抜け','UT(1,10)','RF(100,3)','WT逆張り±53','HMA21','HalfTrend(2,2)','Andean(50,9)','VixFix(22)','Nadaraya-Watson(8,3)','(参考)MACD']
def get(n):
    if n.startswith('MMT '): return x5.SIGS[n[4:]]
    if n in v.SIG: return w.raw(n)
    if n not in x4.CACHE: x4.CACHE[n]=x4.SIG4[n]()
    return x4.CACHE[n]
def combo(A,Bs):
    s=get(A).copy()
    for B in Bs:
        stb=w.state(get(B)); s[(s==1)&(stb!=1)]=0; s[(s==-1)&(stb!=-1)]=0
    return s
def run(a):
    A,Bs,f,cn=a; s=combo(A,Bs); s=t.apply_filter(d,s,f) if f!='none' else s; cfg,sl0=w.CFC[cn]
    return dict(tf=v.TF,A=A,B='|'.join(Bs),flt=f,cfg=cn,**w.evalrun(s,cfg,sl0))
if __name__=='__main__':
    M=['MMT '+m for m in MM]
    pairs=[(a,b) for a in M for b in OT]+[(a,b) for a in OT for b in M]+[(a,b) for a in M for b in M if a!=b]
    A=[(a,(b,),f,cn) for a,b in pairs for f in ('none','h4adx') for cn in w.CFC]
    for a in ('DIクロス','ST(10,3)','SQZ勢い0'):
        for b in M:
            for c_ in OT:
                if c_!=a:
                    for cn in ('買増し無し','ナンピン2'): A.append((a,(b,c_),'h4adx',cn))
    for n in set(x for aa in A for x in (aa[0],)+aa[1]): get(n)
    with Pool() as pl: rows=pl.map(run,A,chunksize=8)
    pd.DataFrame(rows).to_csv(f'tf_combo2_{v.TF}.csv',index=False); print(v.TF,len(rows))
