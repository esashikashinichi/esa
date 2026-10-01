"""解析38 第2段: 上位の候補を、1つずつ・2つずつ値を振って最適を決める。前期間/後期間/5期間で確認"""
import tf_model as t, tf_sl as sl, numpy as np, pandas as pd, json, sys
o=t.load_m15(); d=t.Data(o); DAYS=len(set(o.index.date))
P=[np.datetime64(x) for x in ('2024-07-23','2025-01-01','2025-07-01','2026-01-01','2026-05-01','2026-09-22')]
IDX=[max(200,int(np.searchsorted(o.index.values,x))) for x in P]; SEGS=list(zip(IDX[:-1],IDX[1:])); CUT=IDX[3]
# cfg = (nl,nstep,nmult,pl,pstep,pmult,tp,frac,trail,sl,slip)
def run(ev,cfg,spr=None):
    r=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200,spr=spr)
    F=sl.summarize(r,200,d.N,SEGS,DAYS); A=sl.summarize(r,200,CUT,[(200,CUT)],DAYS); B=sl.summarize(r,CUT,d.N,[(CUT,d.N)],DAYS)
    F['is_pf']=A['pf']; F['oos_pf']=B['pf']; F['is_pnl']=A['pnl']; F['oos_pnl']=B['pnl']; F['segpos']=sum(x>0 for x in F['seg_pnl'])
    F['mpf']=min(A['pf'],B['pf']); F['ratio']=F['pnl']/max(F['dd'],1); return F
BASES={
 'R rsi2+H4+ADX・ピラミッド2':('rsi2','h4adx',(0,1,1,2,1.0,1.0,0.5,0.3,4,5.0,0.1)),
 'D don100+H1H4・ピラミッド2':('don100','h1h4',(0,1,1,2,1.0,1.0,0.5,0.3,4,12.0,0.1)),
 'N pb_ema+H4・ナンピン2':('pb_ema','h4',(2,1,1.5,0,1,1,0.75,0.3,4,12.0,0.1)),
}
SWEEP={'sl':(9,[3,3.5,4,4.5,5,5.5,6,7,8,10,12]),'tp':(6,[0.3,0.4,0.5,0.6,0.75,1.0]),'frac':(7,[0.2,0.3,0.4,0.5,0.7,1.0]),'trail':(8,[2,3,4,5,6]),
       'pl':(3,[0,1,2,3,4]),'pstep':(4,[0.5,0.75,1.0,1.5]),'pmult':(5,[0.5,0.75,1.0]),'nl':(0,[0,1,2,3]),'nstep':(1,[1,1.5,2,3]),'nmult':(2,[1.0,1.25,1.5,2.0])}
def line(x): return f"n={x['n']} 勝率{x['win']:.1f}% PF{x['pf']:.2f}(前{x['is_pf']:.2f}/後{x['oos_pf']:.2f}) 損益{x['pnl']:.0f}円 落込{x['dd']:.0f} 最大損{x['worst']:.0f} 損切り{x['sl_pct']:.1f}% 1日{x['epd']:.2f}回 5期間+{x['segpos']} 比{x['ratio']:.1f}"
if __name__=='__main__':
    for name,(e,fl,base) in BASES.items():
        s=t.apply_filter(d,t.signals(d,e),fl); ev=sl.make_events(d,s)
        print('=====',name,e,fl,base); print('  基準:',line(run(ev,base)))
        for k,(ix,vals) in SWEEP.items():
            if k in('nl','nstep','nmult') and name.startswith(('R','D')) and k!='nl': continue
            print(f'  -- {k}')
            for v in vals:
                c=list(base); c[ix]=float(v) if k=='sl' else v; x=run(ev,tuple(c)); print(f'     {k}={v}:',line(x))
        print('  -- sl×tp')
        for sv in (3,4,5,6,8,12):
            row=[]
            for tp in (0.4,0.5,0.6,0.75):
                c=list(base); c[9]=float(sv); c[6]=tp; x=run(ev,tuple(c)); row.append(f'tp{tp}:PF{x["pf"]:.2f}/比{x["ratio"]:.1f}/+{x["segpos"]}')
            print(f'     sl={sv}: ',' | '.join(row))
