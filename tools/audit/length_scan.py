"""XM note-length audit: compare converter durations (interval capped at 4 beats) with audible length."""
import os, sys, struct
from collections import Counter
ROOT=sys.argv[1]; SKIP={'doubles','Copie de DIVERS','Conversions Ableton Live','xm2live_converted_tracks'}
def parse(d):
    hs=struct.unpack_from('<I',d,60)[0]
    songlen,restart,nch,npat,ninst,flags,speed,bpm=struct.unpack_from('<8H',d,64)
    order=list(d[80:80+songlen]); pos=60+hs; pats=[]
    for p in range(npat):
        hl,pt,rows,ps=struct.unpack_from('<IBHH',d,pos); pos+=hl; data=d[pos:pos+ps]; pos+=ps; q=0; cells=[]
        for r in range(rows):
            row=[]
            for c in range(nch):
                if not ps or q>=len(data): row.append((0,0,0,0,0)); continue
                b=data[q]; q+=1
                if b&0x80:
                    v=[]
                    for bit in range(5):
                        if b&(1<<bit): v.append(data[q] if q<len(data) else 0); q+=1
                        else: v.append(0)
                else: v=[b]+list(data[q:q+4]); q+=4; v+=[0]*(5-len(v))
                row.append(tuple(v))
            cells.append(row)
        pats.append(cells)
    insts={}
    for i in range(ninst):
        isz=struct.unpack_from('<I',d,pos)[0]; nsmp=struct.unpack_from('<H',d,pos+27)[0]
        if nsmp:
            shs=struct.unpack_from('<I',d,pos+29)[0]; voltype=d[pos+233]; spos=pos+isz; tot=0; s0=None
            for s in range(nsmp):
                ln,ls,ll,vol,ft,typ,pan,rel=struct.unpack_from('<IIIBbBBb',d,spos)
                if s==0: s0=dict(frames=ln//(2 if typ&0x10 else 1),loop=typ&3,rel=rel,ft=ft,env=bool(voltype&1))
                tot+=ln; spos+=shs
            insts[i+1]=s0; pos=spos+tot
        else: pos+=isz
    return order,pats,speed,bpm,nch,insts
st=Counter(); files=Counter()
for dp,dns,fns in os.walk(ROOT):
    dns[:]=[x for x in dns if x not in SKIP]
    for fn in fns:
        if not fn.lower().endswith('.xm'): continue
        d=open(os.path.join(dp,fn),'rb').read()
        if not d.startswith(b'Extended Module:'): continue
        try: order,pats,speed,bpm,nch,insts=parse(d)
        except Exception: continue
        if not speed or not bpm: continue
        beat_sec=4*speed*2.5/bpm
        ev={}  # channel -> list of (time_beats, kind, note, inst)
        t=0.0; last={}
        for p in order:
            if p>=len(pats): continue
            for r,row in enumerate(pats[p]):
                for c,(n,i,v,e,pr) in enumerate(row):
                    if i: last[c]=i
                    tb=t+r/4
                    if 0<n<97 and c in last: ev.setdefault(c,[]).append((tb,'note',n,last[c]))
                    elif n==97: ev.setdefault(c,[]).append((tb,'keyoff',0,0))
                    elif v==0x10: ev.setdefault(c,[]).append((tb,'vol0',0,0))
            t+=len(pats[p])/4
        fs=Counter()
        for c,L in ev.items():
            for k,(tb,kind,n,i) in enumerate(L):
                if kind!='note': continue
                s=insts.get(i)
                if not s or not s['frames']: continue
                nxt=L[k+1] if k+1<len(L) else None
                interval=(nxt[0]-tb) if nxt else 1e9
                rate=8363*2**((n-1+s['rel']-48)/12+((s['ft']>>3)*6.25)/1200)
                natural=1e9 if s['loop'] else s['frames']/rate/beat_sec
                audible=min(interval,natural)
                conv=min(interval,4.0) if nxt else 4.0
                fs['notes']+=1
                if audible>4.0+1e-6 and conv<audible-1e-6: fs['cut_by_cap']+=1
                if s['loop'] and interval>4.0+1e-6: fs['looped_cut']+=1
                if natural<conv-0.25: fs['note_longer_than_sample']+=1
                if nxt and nxt[1]=='keyoff':
                    fs['ends_on_keyoff']+=1
                    if not s['env']: fs['keyoff_no_env']+=1
        for k,v in fs.items():
            st[k]+=v
            if v and k!='notes': files[k]+=1
        files['n']+=1
print(f"{files['n']} XM files, {st['notes']} notes")
for k,lbl in [('cut_by_cap','audible sound cut by the 4-beat cap'),('looped_cut','  of which looped samples (pads) cut'),('note_longer_than_sample','MIDI note longer than the sample itself (>1 row)'),('ends_on_keyoff','note followed by a key-off (now ignored; note runs to next note)'),('keyoff_no_env','  key-off on instrument without envelope (FT2 cuts instantly)')]:
    print(f"{lbl:66s} {st[k]:7d} notes ({100*st[k]/st['notes']:4.1f}%) in {files[k]} files")
