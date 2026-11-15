import numpy as np
def reversals(x):
    x=np.asarray(x,float); d=np.diff(x); keep=[0]
    s=np.sign(d); s[s==0]=0
    last=0
    for i in range(1,len(x)-1):
        if (x[i]-x[keep[-1]])*(x[i+1]-x[i])<0: keep.append(i)
    keep.append(len(x)-1)
    return x[keep]
def rainflow(x):
    """ASTM E1049 dört nokta yöntemi; (aralık, ortalama, sayı) listesi döner (sayı 0.5 veya 1)."""
    r=reversals(x); st=[]; out=[]
    for p in r:
        st.append(p)
        while len(st)>=3:
            X=abs(st[-1]-st[-2]); Y=abs(st[-2]-st[-3])
            if X<Y: break
            if len(st)==3:
                out.append((Y,(st[-2]+st[-3])/2,0.5)); st.pop(0)
            else:
                out.append((Y,(st[-2]+st[-3])/2,1.0)); del st[-3:-1]
    for i in range(len(st)-1):
        out.append((abs(st[i+1]-st[i]),(st[i+1]+st[i])/2,0.5))
    return out
