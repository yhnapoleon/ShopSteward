"""Audit saved official web-tool extracts, including pagination completeness.

This is format-normalized text evidence, NOT downloaded PDF/HTML bytes.
"""
import json
import re
from pathlib import Path

BASE=Path(__file__).resolve().parent/'expansion_20260908'
MARK=re.compile(r'L(\d+)(?:@P([0-9-]+))?: ?')
TOKEN=re.compile(r'\ue200cite\ue202\d+\u2020([^\ue201]+)\ue201')

def clear_cites(s):
    return TOKEN.sub(lambda m:m[1].split('\u2020')[0],s).strip()

def extract(paths):
    lines={};page_labels={};conflicts=[];totals=set();url=None;reported_pages=None
    for p in paths:
        text=p.read_text(encoding='utf8')
        u=re.search(r'\((https://[^)]+)\)',text)
        if u:url=u[1]
        n=re.search(r'Total lines: (\d+)',text)
        if n:totals.add(int(n[1]))
        n=re.search(r'Number of pages: (\d+)',text)
        if n:reported_pages=int(n[1])
        matches=list(MARK.finditer(text))
        for j,m in enumerate(matches):
            k=int(m[1]);s=clear_cites(text[m.end():matches[j+1].start() if j+1<len(matches) else len(text)])
            if k in lines and lines[k]!=s:
                if s.startswith(lines[k]):pass
                elif lines[k].startswith(s):continue
                else:conflicts.append({'line':k,'a':lines[k],'b':s})
            lines[k]=s;page_labels[k]=m[2]
    assert len(totals)<=1,totals
    total=next(iter(totals),0)
    missing=[i for i in range(total) if i not in lines]
    groups=[]
    for n in missing:
        if groups and groups[-1][1]==n-1:groups[-1][1]=n
        else:groups.append([n,n])
    return dict(url=url,total_lines=total,lines=lines,page_labels=page_labels,reported_pages=reported_pages,missing=groups,conflicts=conflicts)

if __name__=='__main__':
    result=[]
    for key in sorted({re.sub(r'-\d+\.txt$','',p.name) for p in (BASE/'web-evidence').glob('nsw-*.txt')}):
        paths=sorted((BASE/'web-evidence').glob(key+'-[0-9]*.txt'))
        d=extract(paths)
        item={'key':key,'url':d['url'],'pages':d['reported_pages'],'total_lines':d['total_lines'],'missing':d['missing'],'conflicts':d['conflicts'],'words':len(' '.join(d['lines'].values()).split())}
        if d['reported_pages'] is None:
            # NSW publication body begins after its print/download toolbar.
            starts=[i+1 for i,t in d['lines'].items() if 'download Download as PDF' in t]
            start=max(starts,default=None)
            item.update(body_start=start,body_words=len(' '.join(t for i,t in d['lines'].items() if start is not None and i>=start and 'Was this page helpful?' not in t).split()))
        result.append(item)
        print(json.dumps(item,ensure_ascii=True))
    (BASE/'web-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
