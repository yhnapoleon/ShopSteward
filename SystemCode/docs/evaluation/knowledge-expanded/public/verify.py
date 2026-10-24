"""Offline evidence verification; not application or root-dependency tests."""
import hashlib
import itertools
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
from acquire import ROOT, Tree, Node, sha
from pypdf import PdfReader

CORPUS=ROOT.parent
REQUIRED='source_family_id document_fixture_id version_fixture_id title publisher url source_url language jurisdiction publication_date retrieved_at acquisition_status use_terms_status source_kind original_path content_sha256 size_bytes mime synthetic'.split()

def leaves(n):
    if n.tag in {'script','style','nav','form','button','noscript'}:return []
    return [s for c in n.children for s in ([re.sub(r'\s+',' ',c).strip()] if isinstance(c,str) else leaves(c))]

def main():
    manifest=CORPUS/'public-sources.jsonl'
    records=[json.loads(line) for line in manifest.read_text(encoding='utf8').splitlines()]
    failures=[]
    details=[]
    shingles={}
    for r in records:
        missing=set(REQUIRED)-set(r)
        assert not missing,(r['source_family_id'],missing)
        assert r['synthetic'] is False and r['acquisition_status']=='acquired'
        for key,hkey,skey in [('original_path','content_sha256','size_bytes'),('normalized_path','normalized_sha256','normalized_size_bytes')]:
            p=(CORPUS/r[key]).resolve()
            assert p.is_relative_to(CORPUS.resolve()) and p.is_file(),r[key]
            assert sha(p.read_bytes())==r[hkey] and p.stat().st_size==r[skey],r[key]
        for t in r['terms_evidence']:
            assert sha((CORPUS/t['path']).read_bytes())==t['sha256']
        loc=json.loads((CORPUS/r['locator_path']).read_text(encoding='utf8'))
        assert len(loc)==r['locator_count'] and len(loc)>0
        norm=(CORPUS/r['normalized_path']).read_text(encoding='utf8')
        assert norm.startswith('# '+r['title']+'\n')
        body=norm.split('\n---\n\n',1)[1]
        info={'source_family_id':r['source_family_id'],'original_hash_and_size':'pass','normalized_hash_and_size':'pass','terms_hashes':'pass','locator_count':len(loc)}
        if r['mime']=='text/html':
            tree=Tree((CORPUS/r['original_path']).read_text(encoding='utf8')).root
            nodes=tree.find(lambda n:'gem-c-govspeak' in n.attrs.get('class','').split())
            assert len(nodes)==1
            original=nodes[0]
            fragments=[t for t in leaves(original) if len(t)>=15]
            flat=re.sub(r'\s+',' ',body)
            absent=[f for f in fragments if f not in flat]
            if absent:failures.append({'family':r['source_family_id'],'missing_source_fragments':absent})
            headings=original.find(lambda n:bool(re.fullmatch('h[1-6]',n.tag)))
            assert len(headings)==len(loc)
            for heading,locator in zip(headings,loc):
                assert locator['heading']==re.sub(r'\s+',' ',heading.text()).strip()
                if locator['origin_id']:assert heading.attrs.get('id')==locator['origin_id']
            tables=original.find(lambda n:n.tag=='table')
            assert len(tables)==body.count('<table')
            info.update(source_text_fragments_checked=len(fragments),missing_source_fragments=len(absent),html_tables_preserved=len(tables),linked_images_not_acquired=len(r['linked_images']))
            text=' '.join(leaves(original))
        else:
            original=PdfReader(CORPUS/r['original_path'])
            assert len(original.pages)==r['page_count']==len(loc)
            if r['source_family_id']=='FSA-SFBB-CATERERS':
                pages=json.loads((ROOT/'provenance/fsa-sfbb-page-text.json').read_text(encoding='utf8'))['pages']
            else:pages=[p.extract_text() or '' for p in original.pages]
            for i,p in enumerate(pages,1):
                assert f'## Original PDF page {i}\n' in body
                assert p.replace('\r\n','\n').replace('\r','\n').strip() in body
            info.update(pdf_pages_checked=len(pages),embedded_text_preserved=True,ocr_run=False,sparse_text_pages=r['sparse_text_pages'])
            text=' '.join(pages)
        tokens=re.findall(r'\w+',text.lower())
        shingles[r['source_family_id']]={tuple(tokens[i:i+5]) for i in range(len(tokens)-4)}
        details.append(info)
    assert len(records)==len({r['source_family_id'] for r in records})==len({r['content_sha256'] for r in records})==len({r['document_fixture_id'] for r in records})==len({r['version_fixture_id'] for r in records})==24
    assert not failures,failures
    pairs=[]
    for a,b in itertools.combinations(shingles,2):
        left,right=shingles[a],shingles[b]
        score=len(left&right)/len(left|right)
        pairs.append({'left':a,'right':b,'word_5gram_jaccard':round(score,6),'shorter_document_containment':round(len(left&right)/min(len(left),len(right)),6)})
    pairs.sort(key=lambda p:p['word_5gram_jaccard'],reverse=True)
    certificate={'verified_at':datetime.now(timezone.utc).isoformat(),'status':'pass','manifest_sha256':sha(manifest.read_bytes()),'documents':len(records),'batch_counts':dict(Counter(r['acquisition_batch'] for r in records)),'original_bytes':sum(r['size_bytes'] for r in records),'normalized_bytes':sum(r['normalized_size_bytes'] for r in records),'source_word_count_whitespace_approximate':sum(r['source_body_word_count'] for r in records),'mime_counts':dict(Counter(r['mime'] for r in records)),'pdf_pages':sum(r.get('page_count',0) for r in records),'exact_hash_duplicates':0,'pairs_compared':len(pairs),'similarity_method':'Jaccard and containment of lowercase Unicode word 5-gram sets on source body text; not semantic duplicate proof. Manual family review also required.','highest_similarity_pairs':pairs[:10],'failures':failures,'documents_detail':details,'visual_review':{'scope':'sampled; not exhaustive','samples':[{'file':'hse-cais12.pdf','pdf_pages':[2]},{'file':'hse-cais24.pdf','pdf_pages':[6]},{'file':'fsa-recalls.pdf','pdf_pages':[1,53,54]},{'file':'fsa-sfbb.pdf','pdf_pages':[1,2,5,92]}],'findings':['CAIS12 contains tables whose layout is authoritative only in PDF.','CAIS24 last-page publication footer uses CAIS23; preserved as source anomaly.','Recall pages 53/54 are image-only example posters apart from headings; missing image text explicitly flagged.','SFBB includes blank forms, diagram layouts and photos; normalization preserves embedded text, not filled-in business records.']}}
    (ROOT/'provenance/verification.json').write_text(json.dumps(certificate,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in certificate.items() if k not in ['documents_detail','visual_review']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
