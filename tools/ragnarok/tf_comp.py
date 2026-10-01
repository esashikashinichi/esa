"""解析42: 複利(残高に応じてロットを増やす)の検証。R(RSI2<10 + H4 + ADX + ピラミッディング2段)、M15 2.2年、初期資金1万円。"""
import numpy as np, pandas as pd, tf_model as t, tf_sl4 as sl, tf_pyr as p
d=p.d; o=p.o; YEN=t.YEN; E0=10000.0
CFG={'R(×1.0)':p.cfg(2,1.0,1.0,0.5,0.3,4,0,0),'R ×1.5':p.cfg(2,1.0,1.5,0.5,0.3,4,0,0),'R 逆ピラミッド×0.5':p.cfg(2,1.0,0.5,0.3,0.3,4,0,0)}
def curve(r,i0,i1):
    eqc=E0+r['eqc'][i0:i1]*YEN; eqa=E0+r['eqa'][i0:i1]*YEN; pk=np.maximum.accumulate(eqc)
    dd=((pk-eqa)/np.maximum(pk,1)).max()*100; return eqc,eqa,dd
def report(name,r,i0,i1,idx):
    eqc,eqa,dd=curve(r,i0,i1); yrs=(idx[i1-1]-idx[i0]).days/365.25
    fin=eqc[-1]; cagr=(fin/E0)**(1/yrs)-1 if fin>0 else -1
    tr=[x for x in r['trades'] if i0<=x[1]<i1]; lots=max((x[4] for x in tr),default=0)
    return dict(name=name,final=fin,cagr=100*cagr,dd=dd,minE=eqa.min(),maxlot=r['maxtot']*0.01,N=len(tr),yrs=yrs)
if __name__=='__main__':
    ev=p.ev('R'); idx=o.index
    # 固定ロットは倍率を掛け直す(comp なしの結果を倍率倍)
    out=[]
    base={cn:sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200) for cn,cfg in CFG.items()}
    for cn,cfg in CFG.items():
        for m in (1,3,5,10):
            r=base[cn]; rr=dict(eqc=r['eqc']*m,eqa=r['eqa']*m,trades=[(x[0]*m,x[1],x[2],x[3],x[4]*m) for x in r['trades']],maxtot=r['maxtot']*m)
            out.append(dict(cfg=cn,rule=f'固定{0.01*m:.2f}',**report('',rr,200,d.N,idx)))
        for K in (500,1000,2000,3000,5000):
            for mm in (30,100):
                r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,comp=(E0,K,mm)); out.append(dict(cfg=cn,rule=f'複利 K={K} 上限{mm*0.01:.2f}lot',**report('',r,200,d.N,idx)))
    x=pd.DataFrame(out).drop(columns=['name']); x.to_csv('tf_comp.csv',index=False)
    pd.set_option('display.width',250); print(x.round(1).to_string())
