import pandas as pd, numpy as np
import os
DATA=os.environ.get("RAGNAROK_DATA","data")
m=pd.read_csv(DATA+'/'+os.environ.get('M1FILE','GOLDmicro1.csv')+'',header=None,names=['d','tm','o','h','l','c','v'])
m['t']=pd.to_datetime(m.d+' '+m.tm,format='%Y.%m.%d %H:%M'); m=m.set_index('t')
b=pd.read_pickle(DATA+'/baskets.pkl')
rows=[]
for _,B in b.iterrows():
    legs=B.legs; sgn=1 if B.ty=='buy' else -1
    for i in range(1,len(legs)):
        p,L=legs[i-1],legs[i]
        pb=p['bid']  # bid at prev open (M1 is bid)
        t0=p['t']; t1=L['t']
        if t1>m.index[-1]: continue
        # minute-by-minute from t0+7min to t1
        seq=[]
        for tt in pd.date_range((t0+pd.Timedelta(seconds=420)).floor('min'), t1.floor('min'), freq='min'):
            if tt not in m.index: continue
            r=m.loc[tt]
            adv_open=round((pb-r.o)*sgn*100)   # adverse at bar open
            mom=None
            t3=tt-pd.Timedelta(minutes=3)
            if t3 in m.index: mom=round((r.o-m.loc[t3].c)*sgn*100)  # +: moving in favour
            seq.append((tt.strftime('%H:%M'),adv_open,mom))
        rows.append(dict(bk=f"{B.g}{'B' if B.ty=='buy' else 'S'}@{B.start.strftime('%H:%M')}",leg=i,t_prev=t0.strftime('%H:%M:%S'),t=t1.strftime('%H:%M:%S'),gap=int((t1-t0).total_seconds()),
                 adv_entry=round((pb-L['bid'])*sgn*100),seq=seq))
for r in rows:
    print(f"{r['bk']:10s} leg{r['leg']} {r['t_prev']}->{r['t']} gap={r['gap']:5d} adv={r['adv_entry']:5d}  seq(time,adv@open,mom3)={r['seq'][:12]}")
