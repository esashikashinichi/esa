"""解析35: 案 A1〜A6・B1・B3〜B5 を、基準 S(解析34の一番良い設定)と R(ラグナロク b 型 0.01)に1つずつ足して比べる"""
import ideas_model as m, pandas as pd, numpy as np, json
from multiprocessing import Pool
MID=39196; CUTS=np.linspace(4,m.N,6).astype(int)
BASE={'S':dict(),'R':dict(maxlegs=40,step=1.1,tstop=None,dmax=None)}
def ideas(base):
    L=[('基準',{})]
    for q,W in [(15,240),(15,1440)]:
        for thr in (0.9,1.0,1.1):
            for mode in ('nanpin','both'): L.append(('A1 分散比',dict(vr_q=q,vr_W=W,vr_thr=thr,vr_mode=mode)))
    for W5 in (288,576):
        for k in (1,2,3): L.append(('A2 半減期',dict(hl_k=k,hl_W5=W5)))
    for a in ('fall','highfall'): L.append(('A3 ATR',dict(atr=a)))
    for a in ('buyonly','sellnonanpin'): L.append(('A4 売買の差',dict(asym=a)))
    for nh in [(14,18),(14,20),(12,20)]: L.append(('A5 ナンピン停止時間',dict(nh=nh)))
    L.append(('A6 ロールオーバー',dict(roll=True)))
    if base=='S':
        for fl in (0.5,1.0):
            for tr in (2.0,4.0): L.append(('B1 切ったら逆向き',dict(flip=True,flip_lot=fl,flip_trail=tr,flip_init=tr)))
        for fl in (0.5,1.0): L.append(('B3 段数で逆向き',dict(trig=3,flip_lot=fl,flip_trail=3.0,flip_init=3.0)))
    else:
        for tg in (5,8):
            for fl in (0.5,1.0): L.append(('B3 段数で逆向き',dict(trig=tg,flip_lot=fl,flip_trail=3.0,flip_init=3.0)))
    for p in (0,100): L.append(('B4 ペア決済',dict(pair=p)))
    for g in (1.0,1.3,1.6): L.append(('B5 ロット固定・幅拡大',dict(mult=1.0,grow=g)))
    return [(base,n,kw) for n,kw in L]
def f(a):
    base,name,kw=a; k={**BASE[base],**kw}
    full=m.run(**k); h1=m.run(i1=MID,**k)['pnl']; h2=m.run(i0=MID,**k)['pnl']
    parts=[m.run(i0=x,i1=y,**k)['pnl'] for x,y in zip(CUTS[:-1],CUTS[1:])]
    return dict(base=base,idea=name,kw=json.dumps(kw,ensure_ascii=False),**full,h1=h1,h2=h2,parts=parts,plus=sum(p>0 for p in parts))
if __name__=='__main__':
    cfg=ideas('S')+ideas('R')
    with Pool(4) as p: rows=p.map(f,cfg,chunksize=1)
    D=pd.DataFrame(rows); D.to_csv('ideas.csv',index=False)
    pd.set_option('display.width',250)
    print(D[['base','idea','kw','pnl','h1','h2','max_float','sl','buy','sell','trend','n_trend','n_pair','plus','parts']].to_string(index=False))
