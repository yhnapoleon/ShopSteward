"""Public-only acquisition helper. No credentials, retries, paid APIs or dependency changes.

Run with the repository Python. Files stay within this directory; requests returning
403 are logged and never retried by this helper. Raw responses are audit evidence,
not automatically corpus documents. Metadata/final eligibility require review.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parent

def sha(data):
    return hashlib.sha256(data).hexdigest()

class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or []), []
    def text(self):
        return ''.join(c if isinstance(c, str) else c.text() for c in self.children)
    def find(self, predicate):
        return ([self] if predicate(self) else []) + [n for c in self.children if isinstance(c, Node) for n in c.find(predicate)]

class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break
    def handle_data(self, data):
        self.stack[-1].children.append(data)

def fetch(url, name):
    dest = ROOT / 'provenance' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    record = {'url':url, 'retrieved_at':datetime.now(timezone.utc).isoformat(), 'method':'requests.get; default UA; no auth; no retry'}
    log = ROOT / 'provenance' / 'requests.jsonl'
    if log.exists():
        for line in log.read_text(encoding='utf-8').splitlines():
            prior = json.loads(line)
            if prior['url'] == url:
                return prior
    try:
        r = requests.get(url, timeout=40)
        record.update(http_status=r.status_code, resolved_url=r.url, redirects=[{'url':h.url,'status':h.status_code} for h in r.history], content_type=r.headers.get('Content-Type'), last_modified=r.headers.get('Last-Modified'), etag=r.headers.get('ETag'))
        if r.status_code == 200:
            dest.write_bytes(r.content)
            record.update(path=dest.relative_to(ROOT).as_posix(), sha256=sha(r.content), byte_count=len(r.content))
        else:
            record['error'] = 'HTTP response not acquired as source'
    except requests.RequestException as e:
        record['error'] = type(e).__name__ + ': ' + str(e)
    with log.open('a', encoding='utf-8') as out:
        out.write(json.dumps(record, ensure_ascii=False)+'\n')
    return record

def links(path, base):
    tree = Tree(Path(path).read_text(encoding='utf-8', errors='replace'))
    return [{'title':re.sub(r'\s+',' ',n.text()).strip(), 'url':urljoin(base,n.attrs['href'])} for n in tree.root.find(lambda n:n.tag=='a' and 'href' in n.attrs)]

if __name__ == '__main__':
    if sys.argv[1] == 'fetch':
        for url, name in json.loads(sys.argv[2]):
            print(json.dumps(fetch(url,name),ensure_ascii=False),flush=True)
    elif sys.argv[1] == 'links':
        print(json.dumps(links(sys.argv[2],sys.argv[3]),ensure_ascii=False))
