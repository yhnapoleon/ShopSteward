"""Offline all-page embedded-text extraction; use bundled pypdfium2 runtime.

Leaves original bytes and prior24 files untouched. No OCR or inferred prose.
"""
import hashlib
import json
from pathlib import Path
import pypdfium2 as pdfium

BASE=Path(__file__).resolve().parent/'expansion_20260908'
OUT=BASE/'extracted'
OUT.mkdir(exist_ok=True)
for path in sorted((BASE/'originals').glob('*.pdf')):
    dest=OUT/(path.stem+'.json')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if dest.exists():
        assert json.loads(dest.read_text(encoding='utf8'))['source_sha256']==digest
        continue
    doc=pdfium.PdfDocument(str(path))
    pages=[]
    for page in doc:
        tp=page.get_textpage()
        pages.append(tp.get_text_range())
        tp.close()
        page.close()
    doc.close()
    dest.write_text(json.dumps({'source_sha256':digest,'extractor':'pypdfium2; embedded text only; no OCR','pages':pages},ensure_ascii=False),encoding='utf8')
    print(json.dumps({'file':path.name,'pages':len(pages),'words':len(' '.join(pages).split()),'sparse':[i for i,t in enumerate(pages,1) if len(t.strip())<350]}))
