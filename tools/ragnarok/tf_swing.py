"""解析40: 損切りを上位足(H1/H4)の直近 n 本の高安にする。確定した上位足だけを使う。
買い: 損切り = 直近 n 本の最安値 − buf×ATR、売り: 直近 n 本の最高値 + buf×ATR。距離は ATR 倍に換算(下限1.0)。
cap 超は mode=clip なら cap に切り詰め、skip なら見送り。"""
import itertools, numpy as np, pandas as pd
import tf_model as t, tf_sl2 as sl, tf_m5 as m5
from tf_rsibb import sig
o=t.load_m15(); d=t.Data(o); DAYS=len(set(o.index.date))
def htf_hl(rule,n):
    h=o.H.resample(rule,label='right',closed='right').max().dropna(); l=o.L.resample(rule,label='right',closed='right').min().dropna()
    hh=h.rolling(n).max(); ll=l.rolling(n).min()
    return hh.reindex(o.index,method='ffill').values, ll.reindex(o.index,method='ffill').values
def sdarr(s,rule,n,buf,cap,mode):
    hh,ll=htf_hl(rule,n); out=np.full(d.N,np.nan)
    for i in np.nonzero(s)[0]:
        k=s[i]; a=d.atr[i]
        if not a>0: continue
        if k>0: stop=ll[i]-buf*a; dist=(d.C[i]-stop)/a
        else: stop=hh[i]+buf*a; dist=(stop-d.C[i])/a
        if not dist==dist: continue
        dist=max(dist,1.0)
        if dist>cap:
            if mode=='skip': continue
            dist=cap
        out[i]=dist
    return out
P5=['2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01','2026-09-22']
IDX=[int(np.searchsorted(o.index.values,np.datetime64(x))) for x in P5]; IDX[0]=200
SEG=list(zip(IDX[:-1],IDX[1:])); HALF=int(np.searchsorted(o.index.values,np.datetime64('2026-01-01')))
ENT={'R':('rsi2',None,'h4adx'),'recross2':('rb',(2,2.0),'none'),'recross14':('rb',(14,1.5),'none')}
CFG={ # (nl,ns,nm,pl,pstep,pmult,tp,frac,trail,sl,slip)
 'R型':(0,1,1,2,1.0,1.0,0.5,0.3,4,5.0,0.1),'R型tp0.3':(0,1,1,2,1.0,1.0,0.3,0.3,4,5.0,0.1),
 'ナンピン2+ピラ3':(2,1,1.5,3,1.0,1.0,0.3,0.3,4,5.0,0.1)}
def base_sig(name):
    e,p,f=ENT[name]
    s=t.signals(d,'rsi2') if e=='rsi2' else sig(d,'recross',p[0],20,p[1])
    return t.apply_filter(d,s,f)
def run(s,cfg,sda,i0=200,spr=None):
    ev=sl.make_events(d,s,sda); return sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=i0,spr=spr)
def row(r):
    a=sl.summarize(r,200,d.N,SEG,DAYS); b1=sl.summarize(r,200,HALF,[(200,HALF)],len(set(o.index.date[200:HALF]))); b2=sl.summarize(r,HALF,d.N,[(HALF,d.N)],len(set(o.index.date[HALF:])))
    return dict(N=a['n'],win=a['win'],pf=a['pf'],pnl=a['pnl'],dd=a['dd'],worst=a['worst'],epd=a['epd'],sl_pct=a['sl_pct'],pf_is=b1['pf'],pf_oos=b2['pf'],pos5=sum(1 for x in a['seg_pnl'] if x>0),seg=[round(x) for x in a['seg_pnl']])
if __name__=='__main__':
    rows=[]
    for en in ENT:
        s=base_sig(en)
        for cn,cfg in CFG.items():
            if en=='R' and cn=='ナンピン2+ピラ3': continue
            if en!='R' and cn=='R型': continue
            for slf in (3.0,5.0,8.0):   # 比較用の固定 ATR 倍
                c=list(cfg); c[9]=slf; rows.append(dict(ent=en,cfg=cn,stop=f'固定{slf}ATR',**row(run(s,tuple(c),None))))
            for rule,ns in (('1h',[3,5,10,20]),('4h',[2,3,5,10])):
                for n,buf,cap,mode in itertools.product(ns,(0.0,0.3),(6.0,12.0),('clip','skip')):
                    sda=sdarr(s,rule,n,buf,cap,mode); rows.append(dict(ent=en,cfg=cn,stop=f'{rule} n{n} buf{buf} cap{cap} {mode}',**row(run(s,cfg,sda))))
    x=pd.DataFrame(rows); x.to_csv('tf_swing.csv',index=False); print('全',len(x))
    x['kind']=np.where(x.stop.str.startswith('固定'),'固定',np.where(x.stop.str.startswith('1h'),'H1高安','H4高安'))
    g=x[x.N>=200]
    print('--- 損切りの種類別(取引200以上): 件数 PF中央値 落込中央値 前後PF>1 5期間プラス')
    for (e,c,k),y in g.groupby(['ent','cfg','kind']): print(e,c,k,len(y),round(y.pf.median(),2),round(y.dd.median()),round(100*((y.pf_is>1)&(y.pf_oos>1)).mean()),int((y.pos5==5).sum()))
    print('--- 固定ATR(比較)'); print(x[x.kind=='固定'].drop(columns=['kind']).to_string())
    good=x[(x.kind!='固定')&(x.N>=200)&(x.pf_is>1)&(x.pf_oos>1)&(x.pos5==5)&(x.win>=70)].copy(); good['score']=good.pnl/good.dd
    print('--- 高安の損切りで条件を満たす',len(good),'通り。損益÷落込 上位12'); print(good.sort_values('score',ascending=False).head(12).drop(columns=['kind','score']).to_string())
    print('--- PF 上位8'); print(good.sort_values('pf',ascending=False).head(8).drop(columns=['kind','score']).to_string())
