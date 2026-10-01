"""解析56 第2段: 落ち込みの上限を厳しくして(45/55・35/45・30/40・25/35)、学習で最短の組を選び、未使用期間(M5 2026-04〜09)で検証。
学習の最短だけで選ぶと、未使用期間で崩れる(第1段)ため、上限を絞った時の「学習の上位20個が未使用期間でどれだけ残るか」を見る。"""
import numpy as np, pandas as pd, itertools, pickle, os
import tf_combo_search as cs
from tf_combo_search import *
if __name__=='__main__':
    if os.path.exists('P.pkl'): P=pickle.load(open('P.pkl','rb'))
    else: P=build(); pickle.dump(P,open('P.pkl','wb'))
    mmax=30; TD=[tdays(i0,len(P[(0,si,0)][0]),'M15') for si,i0 in enumerate(STARTS)]
    subs=[c for k in (1,2,3,4) for c in itertools.combinations(range(NC),k)]
    LIMS=[(45,55),(35,45),(30,40),(25,35)]
    rows=[]
    for sub in subs:
        S={(si,sp):tuple(sum(P[(c,si,sp)][k] for c in sub) for k in range(3)) for sp in (0,1) for si in range(len(STARTS))}
        T={(tf,sp):tuple(sum(P[(c,tf,sp)][k] for c in sub) for k in range(3)) for tf in ('M5','T15') for sp in (0,1)}
        tdM=tdays(1,len(T[('M5',0)][0]),'M5'); td15=tdays(iM,len(T[('T15',0)][0]),'M15')
        cache={}
        for Kc in KCS:
            R=[]
            for sp in (0,1):
                a=[sim(*S[(si,sp)],Kc,TD[si],E0,YEN,mmax) for si in range(len(STARTS))]
                R.append(a)
            cache[Kc]=R
        for lim in LIMS:
            for Kc in KCS:
                R=cache[Kc]
                if max(x[1] for x in R[0])<=lim[0] and max(x[1] for x in R[1])<=lim[1]:
                    d3=[x[2] if x[2]>=0 else np.inf for x in R[0]]; d32=[x[2] if x[2]>=0 else np.inf for x in R[1]]
                    o=dict(lim=lim[0],sub=sub,n=len(sub),Kc=Kc,d3=float(np.median(d3)),reach=int(np.isfinite(d3).sum()),dd=max(x[1] for x in R[0]),d3_2=float(np.median(d32)),dd2=max(x[1] for x in R[1]),fmin=min(x[0] for x in R[0]),fmin2=min(x[0] for x in R[1]))
                    for tf,td in (('M5',tdM),('T15',td15)):
                        for sp,lab in ((0,'n'),(1,'s')):
                            f,dd,fr=sim(*T[(tf,sp)],Kc,td,E0,YEN,mmax); o[f'{tf}_{lab}_final']=f; o[f'{tf}_{lab}_dd']=dd
                    rows.append(o); break
    X=pd.DataFrame(rows); X['key']=X['sub'].apply(lambda s:'|'.join(names[c] for c in s)); X.to_pickle('tf_combo2.pkl'); print('done',len(X))
