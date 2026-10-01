"""解析35: B2(ブレイクアウトとの組み合わせ)と C2(出金・ゼロカット)"""
import ideas_model as m, pandas as pd, numpy as np
BASE={'S':dict(),'R':dict(maxlegs=40,step=1.1,tstop=None,dmax=None)}
def daily_eq(r):
    s=pd.Series(r['REAL']+r['FL'],index=m.tt[4:]); return s
def maxdd(x):
    x=np.asarray(x); return float((x-np.maximum.accumulate(x)).min())
if __name__=='__main__':
    eq={b:daily_eq(m.run(log=True,**k)) for b,k in BASE.items()}
    print('== B2 ブレイクアウト単独(0.01ロット)')
    rows=[]
    for ni,no in [(20,10),(55,20),(96,48)]:
        res,dly=m.donchian(ni,no)
        for b in ('S','R'):
            e=eq[b]; dS=e.groupby(e.index.normalize()).last().diff().fillna(e.groupby(e.index.normalize()).last().iloc[0])
            dd=dly.reindex(dS.index).fillna(0)
            corr=np.corrcoef(dS.values,dd.values)[0,1]
            for lot in (0.01,0.02,0.03):
                comb_bar=e.values+ (dd*lot/0.01).cumsum().reindex(e.index.normalize()).values  # 日ごとに確定した分を足す(近似)
                rows.append(dict(base=b,donchian=f'{ni}/{no}',don_pnl=round(res['pnl']*lot/0.01),don_n=res['n'],corr=round(corr,2),lot=lot,
                    base_pnl=round(e.values[-1]),comb_pnl=round(comb_bar[-1]),base_dd=round(maxdd(e.values)),comb_dd=round(maxdd(comb_bar))))
    print(pd.DataFrame(rows).to_string(index=False))
    print('== C2 出金・ゼロカット(資金1万円、許容損失5,000円)')
    out=[]
    for b,e in eq.items():
        E=10000+e
        hit5=E.index[np.argmax(E.values<=5000)] if (E.values<=5000).any() else None
        hit0=E.index[np.argmax(E.values<=0)] if (E.values<=0).any() else None
        # 1) 何もしない(ゼロカット: 0円で終わり) 2) 5,000円で止める 3) 1日の終わりに15,000円以上なら10,000円を残して出金
        r1= 0 if hit0 is not None else E.values[-1]
        r2= E[E.index<hit5].iloc[-1] if hit5 is not None else E.values[-1]
        wd=0.0; off=0.0; ruin=None; last_day=None
        for t,v in E.items():
            cur=v-off
            if cur<=0: ruin=t; break
            d=t.normalize()
            if last_day is not None and d!=last_day and prev>=15000: wd+=prev-10000; off+=prev-10000; cur=v-off
            last_day=d; prev=cur
        r3=wd+(0 if ruin is not None else E.values[-1]-off)
        out.append(dict(base=b,final=round(E.values[-1]),min=round(E.min()),hit5000=str(hit5),hit0=str(hit0),
                        nothing=round(r1),stop5000=round(r2),withdraw=round(r3),withdrawn=round(wd),ruin_w=str(ruin)))
    print(pd.DataFrame(out).to_string(index=False))
