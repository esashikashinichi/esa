"""解析39 第2段: RSI×ボリンジャーの入口 + ナンピン + ピラミッディング + 損切り幅"""
import itertools, numpy as np, pandas as pd
import tf_model as t, tf_sl as sl, tf_m5 as m5
from tf_rsibb import sig
o=t.load_m15(); d=t.Data(o); DAYS=len(set(o.index.date))
P5=['2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01','2026-09-22']
IDX=[int(np.searchsorted(o.index.values,np.datetime64(x))) for x in P5]; IDX[0]=200
SEG=list(zip(IDX[:-1],IDX[1:])); HALF=int(np.searchsorted(o.index.values,np.datetime64('2026-01-01')))
df=pd.read_csv('tf_rsibb.csv')
ok=df[(df.N>=300)&(df.pf_is>1)&(df.pf_oos>1)&(df.pos5==5)&(df.win>=70)].sort_values('pf',ascending=False)
ent=ok.drop_duplicates(['typ','n','k','flt'])[['typ','n','k','flt']].head(12).values.tolist()
ent.append(['rsi2base',0,0,'h4adx'])
NAN=[(0,1,1)]+[(nl,ns,nm) for nl in (2,3) for ns in (1,2) for nm in (1.0,1.5)]
PYR=[0,2,3]; TP=[0.3,0.5]; SLS=[5,8,12]
rows=[]
for typ,n,k,flt in ent:
    s=t.signals(d,'rsi2') if typ=='rsi2base' else sig(d,typ,int(n),20,float(k))
    s=t.apply_filter(d,s,flt); ev=sl.make_events(d,s)
    for (nl,ns,nm),pl,tp,slv in itertools.product(NAN,PYR,TP,SLS):
        cfg=(nl,ns,nm,pl,1.0,1.0,tp,0.3,4,float(slv),0.1)
        r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200)
        a=sl.summarize(r,200,d.N,SEG,DAYS); b1=sl.summarize(r,200,HALF,[(200,HALF)],len(set(o.index.date[200:HALF])))
        b2=sl.summarize(r,HALF,d.N,[(HALF,d.N)],len(set(o.index.date[HALF:])))
        rows.append(dict(typ=typ,n=n,k=k,flt=flt,nl=nl,ns=ns,nm=nm,pl=pl,tp=tp,sl=slv,N=a['n'],win=a['win'],pf=a['pf'],pnl=a['pnl'],dd=a['dd'],worst=a['worst'],epd=a['epd'],
          maxlot=a['maxlot'],pf_is=b1['pf'],pf_oos=b2['pf'],pos5=sum(1 for x in a['seg_pnl'] if x>0),seg=[round(x) for x in a['seg_pnl']]))
x=pd.DataFrame(rows); x.to_csv('tf_rsibb_np.csv',index=False); print('全',len(x),'通り')
x['form']=np.where((x.nl>0)&(x.pl>0),'ナンピン+ピラ',np.where(x.nl>0,'ナンピンのみ',np.where(x.pl>0,'ピラのみ','なし')))
g=x[x.N>=300]
print('--- 形別(取引300以上): PF中央値 / 落ち込み中央値 / 前後PF>1 / 5期間プラス / 件数')
for f,y in g.groupby('form'): print(f,round(y.pf.median(),2),round(y.dd.median()),round(100*((y.pf_is>1)&(y.pf_oos>1)).mean()),int((y.pos5==5).sum()),len(y))
good=x[(x.N>=300)&(x.pf_is>1)&(x.pf_oos>1)&(x.pos5==5)&(x.win>=70)].copy()
good['score']=good.pnl/good.dd
print('--- 条件を満たす',len(good),'通り。PF上位12'); print(good.sort_values('pf',ascending=False).head(12).drop(columns=['form','score']).to_string())
print('--- 損益÷落ち込み上位12'); print(good.sort_values('score',ascending=False).head(12).drop(columns=['form','score']).to_string())
print('--- ナンピンを含む形のPF上位8'); print(good[good.nl>0].sort_values('pf',ascending=False).head(8).drop(columns=['form','score']).to_string())
