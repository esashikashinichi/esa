"""解析38: M5 足での答え合わせ。シグナルと ATR は M15 で作り、約定・損切り・利確は M5 足で追う(足の中の順番を M15 より細かく見る)。
M5 のデータは 2026-04-13〜09-21(約5か月)。M1 は使わない。"""
import numpy as np, pandas as pd, tf_model as t, tf_sl as sl
def load_m5(path='../data/GOLDmicro5.csv'):
    d=pd.read_csv(path,header=None,names=['D','T','O','H','L','C','V'])
    d['t']=pd.to_datetime(d['D']+' '+d['T'],format='%Y.%m.%d %H:%M')
    return d.drop_duplicates('t').set_index('t').sort_index()[['O','H','L','C']]
class M5:
    def __init__(self,d):
        self.m=load_m5(); self.O,self.H,self.L,self.C=[self.m[k].values for k in 'OHLC']; self.t=self.m.index.values
        self.t0=self.t[0]; self.days=len(set(self.m.index.date))
        # 最初の M15 足(M5 の開始以降)
        self.i0=int(np.searchsorted(d.o.index.values,self.t0))+1
    def events(self,d,s):
        ev={}; t15=d.o.index.values
        for i in range(max(200,self.i0),d.N-1):
            k=int(s[i])
            if k==0 or np.isnan(d.atr[i]): continue
            j=int(np.searchsorted(self.t,t15[i+1]))
            if j<len(self.t) and self.t[j]==t15[i+1]: ev.setdefault(j,[]).append((k,float(d.atr[i])))
        return ev
    def run(self,d,s,cfg,spr=None):
        ev=self.events(d,s)
        r=sl.engine(self.O,self.H,self.L,self.C,ev,cfg,i0=1,spr=spr)
        n=len(self.O); half=n//2
        return sl.summarize(r,1,n,[(1,half),(half,n)],self.days)
