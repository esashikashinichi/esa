"""解析35: A2(半減期)の周辺の確認と、固定時間との比較、他の案との組み合わせ"""
import ideas_model as m, pandas as pd, numpy as np, json
from multiprocessing import Pool
from ideas_run import f, BASE
if __name__=='__main__':
    cfg=[]
    for b in ('S','R'):
        for t in (1,2,3,4,6): cfg.append((b,'固定時間',dict(tstop=t)))
        for k in (0.5,0.75,1.0,1.25,1.5):
            for W in (192,288,384): cfg.append((b,'A2 周辺',dict(hl_k=k,hl_W5=W)))
        for lo,hi in [(0.5,24),(2,24),(1,12),(1,48)]: cfg.append((b,'A2 上下限',dict(hl_k=1,hl_W5=288,hl_min=lo,hl_max=hi)))
    cfg.append(('S','A2+B4',dict(hl_k=1,hl_W5=288,pair=0)))
    cfg.append(('S','A2+B1',dict(hl_k=1,hl_W5=288,flip=True,flip_lot=1.0,flip_trail=4.0,flip_init=4.0)))
    cfg.append(('S','A2+B4+B1',dict(hl_k=1,hl_W5=288,pair=0,flip=True,flip_lot=1.0,flip_trail=4.0,flip_init=4.0)))
    cfg.append(('R','A2 12段',dict(hl_k=1,hl_W5=288,maxlegs=12)))
    cfg.append(('R','A2 8段',dict(hl_k=1,hl_W5=288,maxlegs=8)))
    with Pool(4) as p: rows=p.map(f,cfg,chunksize=1)
    D=pd.DataFrame(rows); D.to_csv('ideas_a2.csv',index=False)
    pd.set_option('display.width',250)
    print(D[['base','idea','kw','pnl','h1','h2','max_float','sl','n_tstop','plus','parts']].to_string(index=False))
