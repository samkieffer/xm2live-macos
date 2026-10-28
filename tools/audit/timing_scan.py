"""Per-file: notes dropped for missing instrument, and timeline drift from ignored D/B/F/EE effects."""
import os, sys, struct
from collections import Counter
ROOT=sys.argv[1]; SKIP={'doubles','Copie de DIVERS','Conversions Ableton Live','xm2live_converted_tracks'}
MOD_SIGS={b'M.K.':4,b'M!K!':4,b'FLT4':4,b'4CHN':4,b'6CHN':6,b'8CHN':8,b'FLT8':8,b'CD81':8,b'OKTA':8}
def xm_cells(d):
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
    return order,pats,speed,bpm,nch,'xm'
def mod_cells(d):
    sig=d[1080:1084]
    if sig in MOD_SIGS: nch,nsmp,hdr=MOD_SIGS[sig],31,1084
    elif sig[2:]==b'CH' and sig[:2].isdigit(): nch,nsmp,hdr=int(sig[:2]),31,1084
    else: nch,nsmp,hdr=4,15,600
    so=20+nsmp*30; songlen=d[so]; order=list(d[so+2:so+2+128])[:songlen]; pats=[]
    for pn in range(max(order)+1):
        cells=[]
        for r in range(64):
            row=[]
            for c in range(nch):
                o=hdr+(pn*64*nch+r*nch+c)*4
                b0,b1,b2,b3=d[o:o+4] if o+4<=len(d) else (0,0,0,0)
                per=((b0&0xF)<<8)|b1; smp=(b0&0xF0)|(b2>>4)
                row.append((1 if per else 0, smp, 0, b2&0xF, b3))
            cells.append(row)
        pats.append(cells)
    # converter's MOD tempo detection (first F in first 10 played patterns, approx)
    return order,pats,6,125,nch,'mod'
def analyze(order,pats,speed0,bpm0,nch,fmt):
    st=Counter(); last={}
    # converter view: every row of every order entry, constant tempo = initial (XM header / first F for MOD approx)
    conv_rows=sum(len(pats[p]) for p in order if p<len(pats))
    # initial tempo as converter sees it
    sp,bp=speed0,bpm0
    if fmt=='mod':
        for p in order[:10]:
            found=False
            for row in pats[p]:
                for (n,i,v,e,pr) in row:
                    if e==0xF and pr>0:
                        if pr<=0x1F: sp=pr
                        else: bp=pr
                        found=True; break
                if found: break
            if (sp,bp)!=(6,125): break
    conv_row_sec=sp*2.5/bp
    # real playback
    speed,bpm=speed0,bpm0; t=0.0; oi=0; r=0; visited=set(); rows_played=0; skipped_rows=0
    while oi<len(order):
        p=order[oi]
        if p>=len(pats): oi+=1; r=0; continue
        if (oi,r) in visited: break
        visited.add((oi,r))
        row=pats[p][r]; brk=None; jmp=None; pdelay=0
        for c,(n,i,v,e,pr) in enumerate(row):
            if i: last[c]=i
            if 0<n<97 or (fmt=='mod' and n):
                st['notes']+=1
                if not i:
                    st['notes_no_inst']+=1
                    if c in last: st['notes_no_inst_playable']+=1
            if e==0xF and pr:
                if pr<32: speed=pr
                else: bpm=pr
            elif e==0xD: brk=(pr>>4)*10+(pr&0xF)
            elif e==0xB: jmp=pr
            elif e==0xE and pr>>4==0xE: pdelay=pr&0xF
        t+=speed*2.5/bpm*(1+pdelay); rows_played+=1
        if jmp is not None:
            if jmp<=oi: break  # song loops back: end
            skipped_rows+=len(pats[p])-r-1; oi=jmp; r=brk or 0; continue
        if brk is not None:
            skipped_rows+=len(pats[p])-r-1; oi+=1; r=brk if brk<64 else 0; continue
        r+=1
        if r>=len(pats[p]): oi+=1; r=0
    conv_t=conv_rows*conv_row_sec
    st['real_sec']=t; st['conv_sec']=conv_t; st['skipped_rows']=skipped_rows
    st['drift_pct']=100*(conv_t-t)/t if t else 0
    return st
res={}
for dp,dns,fns in os.walk(ROOT):
    dns[:]=[x for x in dns if x not in SKIP]
    for fn in fns:
        ext=fn.lower().rsplit('.',1)[-1]
        if ext not in ('xm','mod'): continue
        d=open(os.path.join(dp,fn),'rb').read()
        try:
            if ext=='xm':
                if not d.startswith(b'Extended Module:'): continue
                res[fn]=(ext,analyze(*xm_cells(d)))
            else: res[fn]=(ext,analyze(*mod_cells(d)))
        except Exception as ex: pass
for fmt in ('xm','mod'):
    R={k:v for k,(f,v) in res.items() if f==fmt}; n=len(R)
    noinst=[k for k,v in R.items() if v['notes_no_inst_playable']]
    tot=sum(v['notes'] for v in R.values()); lost=sum(v['notes_no_inst_playable'] for v in R.values())
    print(f'\n== {fmt.upper()} {n} files')
    print(f'notes without instrument (playable, currently DROPPED): {len(noinst)} files, {lost}/{tot} notes ({100*lost/tot:.1f}%)')
    worst=sorted(R.items(),key=lambda kv:-kv[1]['notes_no_inst_playable']/max(1,kv[1]['notes']))[:5]
    print('  worst:',[(k,f"{100*v['notes_no_inst_playable']/v['notes']:.0f}%") for k,v in worst])
    drift=[(k,v['drift_pct'],v['skipped_rows']) for k,v in R.items()]
    for th in (1,5,20):
        print(f'timeline off by >{th}% vs real playback: {sum(1 for _,d,_ in drift if abs(d)>th)} files')
    print('  with skipped rows (Dxx/Bxx):',sum(1 for _,_,s in drift if s), ' worst:',[(k,f'{d:+.0f}%') for k,d,_ in sorted(drift,key=lambda x:-abs(x[1]))[:6]])
