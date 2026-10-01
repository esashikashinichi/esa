"""解析44: MACD を入口にした形と、他の条件との組み合わせ(AND)。出口は R と同じ形(部分利確 + 追いかけ、損切り 5 ATR)。
MACD = EMA12 − EMA26、シグナル = MACD の EMA9、ヒストグラム = MACD − シグナル。
入口(買い。売りは逆): hcross = ヒストグラムが 0 を上抜け / zero = MACD が 0 を上抜け / pb = MACD > 0 の間にヒストグラムが 0 を上抜け(押しの終わり)
  pb2 = MACD > 0 かつ シグナル > 0 の間にヒストグラムが 0 を上抜け / hup = MACD > 0 でヒストグラムが負のまま2本連続で上向き
組み合わせ: 上位足(H4・H1・ADX)、RSI2 が直近5本で 20 未満(売りは 80 超)に触れた、EMA20 に直近3本で触れた、終値 > EMA50 > EMA200"""
import itertools, numpy as np, pandas as pd
from multiprocessing import Pool
import tf_model as t, tf_sl3 as sl, tf_pyr as p, tf_m5 as m5
d=p.d; o=p.o; DAYS=p.DAYS; SEG=p.SEG; HALF=p.HALF
c=pd.Series(d.C,index=o.index); ml=t.ema(c,12)-t.ema(c,26); sg=t.ema(ml,9); hist=(ml-sg).values; ml=ml.values; sg=sg.values
P=lambda a:np.r_[np.nan,a[:-1]]
def entry(typ):
    s=np.zeros(d.N,int)
    if typ=='hcross': s[(hist>0)&(P(hist)<=0)]=1; s[(hist<0)&(P(hist)>=0)]=-1
    elif typ=='zero': s[(ml>0)&(P(ml)<=0)]=1; s[(ml<0)&(P(ml)>=0)]=-1
    elif typ=='pb': s[(ml>0)&(hist>0)&(P(hist)<=0)]=1; s[(ml<0)&(hist<0)&(P(hist)>=0)]=-1
    elif typ=='pb2': s[(ml>0)&(sg>0)&(hist>0)&(P(hist)<=0)]=1; s[(ml<0)&(sg<0)&(hist<0)&(P(hist)>=0)]=-1
    elif typ=='hup':
        h1=P(hist); h2=np.r_[np.nan,np.nan,hist[:-2]]
        s[(ml>0)&(hist<0)&(hist>h1)&(h1>h2)]=1; s[(ml<0)&(hist>0)&(hist<h1)&(h1<h2)]=-1
    s[:300]=0; return s
r2=pd.Series(d.r2,index=o.index); dip_lo=(r2.rolling(5).min()<20).values; dip_hi=(r2.rolling(5).max()>80).values
touch_lo=(pd.Series(d.L,index=o.index)<=pd.Series(d.e20,index=o.index)).rolling(3).max().values>0
touch_hi=(pd.Series(d.H,index=o.index)>=pd.Series(d.e20,index=o.index)).rolling(3).max().values>0
def filt(s,f):
    s=s.copy()
    if f=='none': return s
    if f in('h4','h1h4','h4adx'): return t.apply_filter(d,s,f)
    if f=='rsi2dip': s[(s==1)&~dip_lo]=0; s[(s==-1)&~dip_hi]=0; return s
    if f=='h4adx+rsi2dip': s=t.apply_filter(d,s,'h4adx'); return filt(s,'rsi2dip')
    if f=='ema20touch': s[(s==1)&~touch_lo]=0; s[(s==-1)&~touch_hi]=0; return s
    if f=='trend3': s[(s==1)&~((d.C>d.e50)&(d.e50>d.e200))]=0; s[(s==-1)&~((d.C<d.e50)&(d.e50<d.e200))]=0; return s
    if f=='h4adx+trend3': s=t.apply_filter(d,s,'h4adx'); return filt(s,'trend3')
    if f=='h1h4+ema20touch': s=t.apply_filter(d,s,'h1h4'); return filt(s,'ema20touch')
FIL=['none','h4','h1h4','h4adx','rsi2dip','h4adx+rsi2dip','ema20touch','trend3','h4adx+trend3','h1h4+ema20touch']
CF={'R型 段2 利確0.5':p.cfg(2,1.0,1.0,0.5,0.3,4,0,0),'段2 利確0.3':p.cfg(2,1.0,1.0,0.3,0.3,4,0,0),'買増し無し 利確0.5':p.cfg(0,1.0,1.0,0.5,0.3,4,0,0)}
def run(a):
    typ,f,cn=a; s=filt(entry(typ),f); ev=sl.make_events(d,s); r=sl.engine(d.O,d.H,d.L,d.C,ev,CF[cn],i0=200)
    x=sl.summarize(r,200,d.N,SEG,DAYS); b1=sl.summarize(r,200,HALF,[(200,HALF)],len(set(o.index.date[200:HALF]))); b2=sl.summarize(r,HALF,d.N,[(HALF,d.N)],len(set(o.index.date[HALF:])))
    return dict(typ=typ,flt=f,cfg=cn,N=x['n'],win=x['win'],pf=x['pf'],pnl=x['pnl'],dd=x['dd'],worst=x['worst'],epd=x['epd'],pf_is=b1['pf'],pf_oos=b2['pf'],pos5=sum(1 for v in x['seg_pnl'] if v>0),seg=[round(v) for v in x['seg_pnl']])
if __name__=='__main__':
    A=[(ty,f,cn) for ty in ('hcross','zero','pb','pb2','hup') for f in FIL for cn in CF]
    with Pool() as pl: rows=pl.map(run,A,chunksize=4)
    x=pd.DataFrame(rows); x['score']=x.pnl/x.dd; x.to_csv('tf_macd.csv',index=False); pd.set_option('display.width',250)
    print('全',len(x),'通り')
    g=x[x.N>=100]
    print('--- MACD 単体(フィルター無し)の入口別(R型 段2 利確0.5)'); print(g[(g.flt=='none')&(g.cfg=='R型 段2 利確0.5')].drop(columns=['score','seg','cfg']).round(2).to_string())
    print('--- 条件別の勝率・PF の中央値(取引100以上)'); print(g.groupby('flt').agg(件数=('pf','size'),勝率=('win','median'),PF=('pf','median'),落込=('dd','median')).round(1).to_string())
    print('--- 入口別'); print(g.groupby('typ').agg(件数=('pf','size'),勝率=('win','median'),PF=('pf','median')).round(2).to_string())
    ok=x[(x.N>=300)&(x.pf_is>1)&(x.pf_oos>1)&(x.pos5==5)]
    print('--- 取引300以上・前期後期とも PF>1・5期間すべてプラス',len(ok),'通り。PF 上位12'); print(ok.sort_values('pf',ascending=False).head(12).drop(columns=['score']).round(2).to_string())
    print('--- 勝率上位8'); print(ok.sort_values('win',ascending=False).head(8).drop(columns=['score']).round(2).to_string())
    print('--- 損益÷落ち込み上位8'); print(ok.sort_values('score',ascending=False).head(8).drop(columns=['score']).round(2).to_string())
    print('--- 参考 R(RSI2<10 + H4 + ADX)'); rb=p.run(('R',CF['R型 段2 利確0.5'])); print({k:(round(v,2) if isinstance(v,float) else v) for k,v in rb.items() if k in('N','win','pf','pnl','dd','worst','epd','pf_is','pf_oos','pos5')})
