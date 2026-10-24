"""Append-only focused expansion acquisition. Prior pilot files are immutable.

Public HTTPS GET only; no credentials, retries or 403 workarounds. Each command
receives an explicit JSON list of URL/name pairs; discovery/terms are not corpus.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests

sys.dont_write_bytecode=True
from acquire import ROOT,sha

EXP=ROOT/'expansion_20260908'
LOG=EXP/'requests.jsonl'

def fetch(url,name):
    EXP.mkdir(exist_ok=True)
    for ledger in [ROOT/'provenance/requests.jsonl',LOG]:
        if ledger.exists():
            for line in ledger.read_text(encoding='utf8').splitlines():
                prior=json.loads(line)
                if prior['url']==url:
                    return {'cached':True,**prior}
    dest=(EXP/name).resolve()
    assert dest.is_relative_to(EXP.resolve()) and not dest.exists()
    record={'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'method':'requests.get; default UA; no credentials; no retry'}
    try:
        r=requests.get(url,timeout=40)
        record.update(http_status=r.status_code,resolved_url=r.url,content_type=r.headers.get('Content-Type'),last_modified=r.headers.get('Last-Modified'),etag=r.headers.get('ETag'),redirects=[{'url':h.url,'status':h.status_code} for h in r.history])
        if r.status_code==200:
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(r.content)
            record.update(path=dest.relative_to(ROOT.parent).as_posix(),sha256=sha(r.content),byte_count=len(r.content))
        else:record['error']='No source body acquired for non-200 response'
    except requests.RequestException as e:
        record['error']=type(e).__name__+': '+str(e)
    with LOG.open('a',encoding='utf8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
    return record

if __name__=='__main__':
    pairs=json.loads(Path(sys.argv[1]).read_text(encoding='utf8')) if sys.argv[1].endswith('.json') else json.loads(sys.argv[1])
    for url,name in pairs:
        r=fetch(url,name)
        print(json.dumps({'name':name,**{k:r[k] for k in ['http_status','byte_count','resolved_url','error','cached'] if k in r}},ensure_ascii=False),flush=True)
