"""解析36: M15 のシグナルを、M1 足(07-17〜09-21)で決済まで追って、M15 だけの計算との差を確かめる"""
import tf_model as t, numpy as np, pandas as pd
o=t.load_m15(); d=t.Data(o)
a=pd.read_csv('../data/M1_long.csv',header=None,names=['D','T','O','H','L','C','V'])
a['t']=pd.to_datetime(a['D']+' '+a['T'],format='%Y.%m.%d %H:%M'); m=a.drop_duplicates('t').set_index('t').sort_index()
mt=m.index.values; MO,MH,ML,MC=[m[k].values for k in 'OHLC']
I0=int(np.searchsorted(o.index.values,np.datetime64('2026-07-18'))); I1=len(o)
def sim_m1(s,exit,tp=1.0,sl=1.0,be=None,trail=None,frac=0.5):
    out=[]; i=I0
    while i<I1-1:
        k=s[i]
        if k==0: i+=1; continue
        t1=o.index.values[i+1]; p=int(np.searchsorted(mt,t1))
        if p>=len(mt) or abs((mt[p]-t1)/np.timedelta64(1,'m'))>5: i+=1; continue
        e=MO[p]; sp=e*t.SPR; at=d.atr[i]; px=e+sp if k>0 else e
        SL=px-k*sl*at; TP=px+k*tp*at if exit in ('fix','part') else None; moved=False; best=px; ex=None; kind=None; q=p; booked=0.0; rem=1.0
        while q<len(mt):
            hi=MH[q]+(sp if k<0 else 0); lo=ML[q]+(sp if k<0 else 0); op=MO[q]+(sp if k<0 else 0); cl=MC[q]+(sp if k<0 else 0)
            fav=hi if k>0 else lo; adv=lo if k>0 else hi
            if (op-SL)*k<=0: ex=op; kind='be' if moved else 'sl'; break
            if TP is not None and (op-TP)*k>=0: ex=op; kind='tp'; break
            if (adv-SL)*k<=0: ex=SL; kind='be' if moved else 'sl'; break
            if exit=='part' and TP is not None and (fav-TP)*k>=0:
                booked=frac*(TP-px)*k; rem=1-frac; TP=None; SL=px+k*sp; moved=True; best=fav
                if (cl-SL)*k<=0: ex=SL; kind='part'; break
                q+=1; continue
            if TP is not None and (fav-TP)*k>=0: ex=TP; kind='tp'; break
            if exit=='fix' and be and not moved and (fav-px)*k>=be*at:
                SL=px+k*sp; moved=True
                if (cl-SL)*k<=0: ex=SL; kind='be'; break
            if exit=='trail' or (exit=='part' and moved):
                best=max(best,fav) if k>0 else min(best,fav); ns=best-k*trail*at
                if (ns-SL)*k>0:
                    SL=ns
                    if (cl-SL)*k<=0: ex=SL; kind='sl'; break
            q+=1
        if ex is None: break
        if exit=='part' and moved: kind='part'
        out.append((i,0,k,booked+rem*(ex-px)*k,kind))
        # 次のシグナルは、決済した M1 の時刻より後の M15 足から
        i=max(i+1,int(np.searchsorted(o.index.values,mt[q],side='right')))
    return out
def check(e,f,ex,**kw):
    s=t.apply_filter(d,t.signals(d,e),f)
    A=t.stats(t.simulate(d,s,ex,i0=I0,**kw)); B=t.stats(sim_m1(s,ex,**kw))
    return A,B
if __name__=='__main__':
    import sys
    for e,f,ex,kw in [('don55','h1h4','fix',dict(tp=3,sl=3,be=0.5)),('rsi2','h4','fix',dict(tp=3,sl=2,be=0.5)),('don55','h1h4','fix',dict(tp=3,sl=3))]:
        A,B=check(e,f,ex,**kw); print(e,f,kw,'\n  M15:',A,'\n  M1 :',B)
