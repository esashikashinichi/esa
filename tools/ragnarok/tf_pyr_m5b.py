import numpy as np, tf_model as t, tf_sl3 as sl, tf_pyr as p, tf_m5 as m5, tf_pyr_m5 as q
C=p.cfg; M=q.M; d=p.d
for en in ('R','rc2','EMA'):
    s=p.entry(en); ev=p.ev(en)
    for lab,cfg in [('基準 段2',C(2,1.0,1.0,0.5,0.3,4,0,0)),('利確後も買い増し 段4・幅1.0・×1.0',C(4,1.0,1.0,0.5,0.3,4,0,1)),('利確後も買い増し 段3・幅1.5・×1.0',C(3,1.5,1.0,0.5,0.3,4,0,1))]:
        r5=sl.engine(M.O,M.H,M.L,M.C,q.ev5(s),cfg,i0=1); x5=sl.summarize(r5,1,len(M.O),[(1,len(M.O))],M.days)
        r5b=sl.engine(M.O,M.H,M.L,M.C,q.ev5(s),cfg,i0=1,spr=t.SPR*2); y5=sl.summarize(r5b,1,len(M.O),[(1,len(M.O))],M.days)
        r15=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=M.i0); x15=sl.summarize(r15,M.i0,d.N,[(M.i0,d.N)],M.days)
        r15f=sl.engine(d.O,d.H,d.L,d.C,ev,cfg,i0=200); xf=sl.summarize(r15f,200,d.N,[(200,d.N)],p.DAYS)
        print(f'{en} {lab}\n   M15全期間:',q.line(xf),'\n   M5      :',q.line(x5),'\n   M5 spr2 :',q.line(y5),'\n   M15同期間:',q.line(x15))
