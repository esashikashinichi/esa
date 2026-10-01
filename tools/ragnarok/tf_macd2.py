"""解析44 第2段: MACD 押し型の M5 答え合わせ・スプレッド2倍と、R との組み合わせ(R に MACD 条件を足す / R との和集合)"""
import numpy as np, tf_model as t, tf_sl3 as sl, tf_pyr as p, tf_macd as mc
d=p.d; o=p.o; DAYS=p.DAYS
M5=__import__('tf_m5').M5(d)
def ev5(s):
    ev={}; t15=o.index.values
    for i in range(max(200,M5.i0),d.N-1):
        k=int(s[i])
        if k==0 or not d.atr[i]>0: continue
        j=int(np.searchsorted(M5.t,t15[i+1]))
        if j<len(M5.t) and M5.t[j]==t15[i+1]: ev.setdefault(j,[]).append((k,float(d.atr[i]),5.0))
    return ev
def line(x): return f"n={x['n']:>4} 勝率{x['win']:.1f}% PF{x['pf']:.2f} 損益{x['pnl']:.0f}円 落込{x['dd']:.0f} 最大損{x['worst']:.0f} 1日{x['epd']:.2f}回"
R=p.entry('R'); mlz=np.nan_to_num(mc.ml)
R_macd=R.copy(); R_macd[(R==1)&~(mlz>0)]=0; R_macd[(R==-1)&~(mlz<0)]=0            # R の入口 + MACD の向きが同じ
PBH4=mc.filt(mc.entry('pb2'),'h4'); PB1=mc.filt(mc.entry('pb'),'h4')
U=np.where(R!=0,R,PBH4)                                                              # R または MACD 押し(H4)
C=mc.CF
CANDS=[('R(基準)',R,C['R型 段2 利確0.5']),('R + MACD の向き',R_macd,C['R型 段2 利確0.5']),
 ('MACD押し pb + H4(段2・利確0.5)',PB1,C['R型 段2 利確0.5']),('MACD押し pb2 + H4(段2・利確0.3)',PBH4,C['段2 利確0.3']),
 ('MACD押し pb2 + H1H4(段2・利確0.3)',mc.filt(mc.entry('pb2'),'h1h4'),C['段2 利確0.3']),
 ('MACD押し pb + RSI2 の押し(段2・利確0.5)',mc.filt(mc.entry('pb'),'rsi2dip'),C['R型 段2 利確0.5']),
 ('R または MACD押し pb2+H4(段2・利確0.5)',U,C['R型 段2 利確0.5']),('R または MACD押し pb2+H4(段2・利確0.3)',U,C['段2 利確0.3'])]
for name,s,cfg in CANDS:
    ev=sl.make_events(d,s); r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200); x=sl.summarize(r,200,d.N,p.SEG,DAYS)
    b1=sl.summarize(r,200,p.HALF,[(200,p.HALF)],len(set(o.index.date[200:p.HALF]))); b2=sl.summarize(r,p.HALF,d.N,[(p.HALF,d.N)],len(set(o.index.date[p.HALF:])))
    r2=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,spr=t.SPR*2); x2=sl.summarize(r2,200,d.N,[(200,d.N)],DAYS)
    e5=ev5(s); r5=sl.engine(M5.O,M5.H,M5.L,M5.C,e5,cfg,i0=1); x5=sl.summarize(r5,1,len(M5.O),[(1,len(M5.O))],M5.days)
    r5b=sl.engine(M5.O,M5.H,M5.L,M5.C,e5,cfg,i0=1,spr=t.SPR*2); y5=sl.summarize(r5b,1,len(M5.O),[(1,len(M5.O))],M5.days)
    r15=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=M5.i0); x15=sl.summarize(r15,M5.i0,d.N,[(M5.i0,d.N)],M5.days)
    print('==',name); print('  M15全期間:',line(x),f"前PF{b1['pf']:.2f}/後PF{b2['pf']:.2f} 5期間+{sum(1 for v in x['seg_pnl'] if v>0)}")
    print('  M15 spr2 :',line(x2)); print('  M5       :',line(x5)); print('  M5 spr2  :',line(y5)); print('  M15同期間:',line(x15))
