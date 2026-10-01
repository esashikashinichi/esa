"""解析46: (A) ナンピンを増やした検証(段数 2〜8・幅・倍率・損切り)、(B) TradingView 系インジケーター同士の組み合わせ(トリガー A + 他の方向確認 B(・C))。
方向確認 = そのインジケーターの直近のシグナルの向き(フリップ型は現在の方向)。TF=M15/M5(環境変数)。"""
import os, sys, itertools, numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl4 as sl, tf_tv as v
d=v.d; o=v.o; N=v.N; idx=v.idx; DAYS=v.DAYS; SEG=v.SEG; HALF=v.HALF; TF=v.TF
def evalrun(s,cfg,sl0):
    ev=sl.make_events(d,s,None,sl0); r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200)
    x=sl.summarize(r,200,N,SEG,DAYS); b1=sl.summarize(r,200,HALF,[(200,HALF)],len(set(idx.date[200:HALF]))); b2=sl.summarize(r,HALF,N,[(HALF,N)],len(set(idx.date[HALF:])))
    return dict(N=x['n'],win=x['win'],pf=x['pf'],pnl=x['pnl'],dd=x['dd'],worst=x['worst'],epd=x['epd'],maxlot=x['maxlot'],pf_is=b1['pf'],pf_oos=b2['pf'],pos=sum(1 for q in x['seg_pnl'] if q>0),nseg=len(x['seg_pnl']))
def state(s):
    a=s.astype(float); a[a==0]=np.nan; return pd.Series(a).ffill().fillna(0).values.astype(int)
IND=['ST(10,3)','ST(10,2)','UT(1,10)','UT(2,10)','RF(100,3)','SQZ発火','SQZ勢い0','WT逆張り±53','WT0クロス','Ichi TK+雲','Ichi 雲抜け','PSAR','HMA21','DIクロス','(参考)MACD']
RAW={}
def raw(n):
    if n not in RAW: RAW[n]=v.SIG[n]()
    return RAW[n]
def combo(A,Bs):
    s=raw(A).copy()
    for B in Bs:
        stb=state(raw(B)); s[(s==1)&(stb!=1)]=0; s[(s==-1)&(stb!=-1)]=0
    return s
CFC={'買増し無し':v.CF['買増し無し'],'ピラ2':v.CF['ピラ2'],'ナンピン2':v.CF['ナンピン2'],'ナンピン2+ピラ2 利確0.3':v.CF['ナンピン2+ピラ2 利確0.3']}
def runcombo(a):
    A,Bs,f,cn=a; s=combo(A,Bs); s=t.apply_filter(d,s,f) if f!='none' else s; cfg,sl0=CFC[cn]
    return dict(tf=TF,A=A,B='+'.join(Bs),flt=f,cfg=cn,**evalrun(s,cfg,sl0))
ENT={'DI+H4':lambda:t.apply_filter(d,raw('DIクロス'),'h4'),'SQZ勢い0+H4':lambda:t.apply_filter(d,raw('SQZ勢い0'),'h4'),'R':lambda:t.apply_filter(d,t.signals(d,'rsi2'),'h4adx'),
     'ST(10,3)+H4':lambda:t.apply_filter(d,raw('ST(10,3)'),'h4'),'Donchian55+H1H4':lambda:t.apply_filter(d,t.signals(d,'don55'),'h1h4')}
ESIG={}
def runnan(a):
    en,nl,ns,nm,slv,pl,tp=a
    if en not in ESIG: ESIG[en]=ENT[en]()
    cfg=(nl,ns,nm,pl,1.0,1.0,tp,0.3,4,float(slv),0.1,0,0)
    return dict(tf=TF,ent=en,nl=nl,ns=ns,nm=nm,sl=slv,pl=pl,tp=tp,**evalrun(ESIG[en],cfg,float(slv)))
if __name__=='__main__':
    mode=sys.argv[1]
    for n in IND: raw(n)
    if mode=='nan':
        A=[(en,nl,ns,nm,slv,pl,tp) for en in ENT for nl in (2,4,6,8) for ns in (0.5,1.0,1.5,2.0) for nm in (1.0,1.5) for slv in (8,15) for pl in (0,2) for tp in (0.3,0.5)]
        with Pool() as pl_: rows=pl_.map(runnan,A,chunksize=8)
        pd.DataFrame(rows).to_csv(f'tf_nan_{TF}.csv',index=False)
    else:
        A=[(a,(b,),f,cn) for a in IND for b in IND if a!=b for f in ('none','h4adx') for cn in CFC]
        top=['DIクロス','ST(10,3)','SQZ勢い0','PSAR','Ichi TK+雲']
        for a in top:
            others=[x for x in IND if x!=a]
            for b,c in itertools.combinations(others,2):
                for cn in ('買増し無し','ナンピン2'): A.append((a,(b,c),'h4adx',cn))
        with Pool() as pl_: rows=pl_.map(runcombo,A,chunksize=8)
        pd.DataFrame(rows).to_csv(f'tf_combo_{TF}.csv',index=False)
    print(mode,TF,len(rows))
