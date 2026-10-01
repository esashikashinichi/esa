"""解析52: 解析51の各候補(選んだ K)を M5 足(2026-04-13〜09-21、約5か月)で複利検証。
シグナルと ATR は M15、約定・損切り・利確は M5 足で追う。比較のため同じ期間の M15 実行も出す。"""
import numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl4 as sl, tf_rank as r, tf_m5 as m5
d=r.d; M=m5.M5(d); E0=r.E0; YEN=t.YEN; p15=d.o.index.values
EV={}
def ev5(name):
    if name in EV: return EV[name]
    s,c,sl0=r.C[name]; ev={}
    for i in range(max(200,M.i0),d.N-1):
        k=int(s[i])
        if k==0 or not d.atr[i]>0: continue
        j=int(np.searchsorted(M.t,p15[i+1]))
        if j<len(M.t) and M.t[j]==p15[i+1]: ev.setdefault(j,[]).append((k,float(d.atr[i]),sl0))
    EV[name]=ev; return ev
def stat(rr,i0,n_ent):
    eqc=E0+rr['eqc'][i0:]*YEN; eqa=E0+rr['eqa'][i0:]*YEN; pk=np.maximum.accumulate(eqc)
    return eqc[-1],((pk-eqa)/pk).max()*100,eqa.min(),n_ent
def run(a):
    name,K=a; s,c,sl0=r.C[name]; out={}
    for lab,spr in (('n',None),('s2',t.SPR*2)):
        e=ev5(name); x=sl.engine(M.O,M.H,M.L,M.C,e,r.cf(c),i0=1,comp=(E0,K,30),spr=spr)
        out['m5_'+lab]=stat(x,1,sum(len(v) for v in e.values()))
        y=sl.engine(d.O,d.H,d.L,d.C,r.ev(name),r.cf(c),i0=M.i0,comp=(E0,K,30),spr=spr)
        out['m15_'+lab]=stat(y,M.i0,0)
    return name,K,out
if __name__=='__main__':
    b=pd.read_csv('tf_rank_best.csv').sort_values('d3'); A=[(n,int(k)) for n,k in zip(b.name,b.K)]
    A+= [(n,2000) for n in b.name[:8] if int(b[b.name==n].K.iloc[0])!=2000]   # 安全側 K=2000 も
    for n in r.C: ev5(n)
    with Pool() as pl: res=pl.map(run,A)
    rows=[]
    for n,K,o in res:
        rows.append(dict(name=n,K=K,**{f'{k}_{f}':round(v[i],1) for k,v in o.items() for i,f in enumerate(('final','dd','min','ent'))}))
    pd.DataFrame(rows).to_csv('tf_rank_m5.csv',index=False); print('done',len(rows))
