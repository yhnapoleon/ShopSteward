"""Build faithful text companions and Singer-compatible public manifest, offline.

Downloaded byte originals remain authoritative. No model-written source body,
translation, image OCR, web-asset downloading or section-as-document expansion.
"""
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.dont_write_bytecode = True
from pypdf import PdfReader
from acquire import ROOT, Node, Tree, sha

CORPUS = ROOT.parent
OGL = 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/'
SELECTED = [
 ('hse-cais17.pdf','HSE-CAIS17','Safety during emptying and cleaning of fryers','Health and Safety Executive','GB','fryer emptying, hot oil, cleaning and equipment isolation'),
 ('hse-cais6.pdf','HSE-CAIS6','Preventing slips and trips in kitchens and food service','Health and Safety Executive','GB','spill response, floor cleaning, footwear and slip prevention'),
 ('hse-cais10.pdf','HSE-CAIS10','Ventilation in catering kitchens','Health and Safety Executive','GB','kitchen extraction, ventilation design and maintenance'),
 ('hse-cais12.pdf','HSE-CAIS12','Maintenance priorities in catering','Health and Safety Executive','GB','equipment maintenance priorities and inspection checklist'),
 ('hse-cais22.pdf','HSE-CAIS22','Safe use of cleaning substances in the hospitality industry','Health and Safety Executive','GB','cleaning chemical handling, storage, dilution and exposure control'),
 ('hse-cais23.pdf','HSE-CAIS23','Gas safety in catering and hospitality','Health and Safety Executive','GB','gas appliances, competent servicing, ventilation and interlocks'),
 ('hse-cais24.pdf','HSE-CAIS24','Preventing manual handling injuries to catering staff','Health and Safety Executive','GB','receipt and movement of loads, lifting aids and task redesign'),
 ('hse-cais26.pdf','HSE-CAIS26','Preventing exposure to carbon monoxide from use of solid fuel appliances in commercial kitchens','Health and Safety Executive','GB','solid-fuel appliances, carbon monoxide and shutdown procedures'),
 ('fsa-freezing.html','FSA-BULK-FREEZING',None,'Food Standards Agency','GB-ENG;GB-WLS;GB-NIR','bulk freezing, date labels, traceability and freezing process'),
 ('fsa-delivery.html','FSA-FOOD-DELIVERY',None,'Food Standards Agency','GB-ENG;GB-WLS;GB-NIR','order handling, delivery vehicles, hygiene and allergen handoff'),
 ('fsa-allergens.html','FSA-ALLERGEN-TECHNICAL',None,'Food Standards Agency','GB-ENG;GB-WLS;GB-NIR','prepacked, loose and PPDS allergens; exemptions and technical labelling'),
 ('fsa-fcm.html','FSA-FOOD-CONTACT-REGULATIONS',None,'Food Standards Agency','GB-ENG;GB-WLS;GB-NIR','packaging and utensil material scope, national regulations and exclusions'),
 ('fsa-biobased.html','FSA-BIOBASED-FCM',None,'Food Standards Agency','GB-ENG;GB-WLS;GB-NIR','biobased packaging sourcing, processing, compliance and end of life'),
 ('defra-labels.html','DEFRA-FOOD-INFORMATION',None,'Department for Environment, Food & Rural Affairs; Food Standards Agency','UK; see GB/NI distinctions in source','food labels, ingredients, quantitative declarations, origin and warnings'),
 ('fsa-acrylamide.html','FSA-ACRYLAMIDE',None,'Food Standards Agency','GB-ENG;GB-WLS;GB-NIR','acrylamide mitigation duties for microbusinesses, retailers and manufacturers'),
 ('defra-plastics.html','DEFRA-SINGLE-USE-PLASTICS',None,'Department for Environment, Food & Rural Affairs','GB-ENG','cups, containers, cutlery and straws; supply bans and exemptions'),
 ('defra-surplus.html','DEFRA-FOOD-WASTE-HIERARCHY',None,'Department for Environment, Food & Rural Affairs; Environment Agency','GB-ENG','surplus prevention, redistribution, animal feed and disposal hierarchy'),
 ('dhsc-calories.html','DHSC-CALORIE-LABELLING',None,'Department of Health and Social Care','GB-ENG','calorie menu labels, business and product exemptions, serving sizes'),
 ('dhsc-promotions.html','DHSC-HFSS-PROMOTIONS',None,'Department of Health and Social Care','GB-ENG','retail placement, multibuy restrictions, business and product exceptions'),
 ('fsa-recalls.pdf','FSA-TRACEABILITY-RECALLS','Guidance on Food Traceability, Withdrawals and Recalls within the UK Food Industry','Food Standards Agency; Food Standards Scotland','UK','traceability records, withdrawal versus recall, notices, responsibilities and root cause analysis'),
 ('dbt-price-marking.html','DBT-PRICE-MARKING',None,'Department for Business and Trade','GB','selling price, unit price, promotions, small-shop exemptions and display requirements'),
 ('opss-packaged-goods.html','OPSS-PACKAGED-GOODS',None,'Office for Product Safety and Standards','GB','package quantities, packers and importers, average and minimum systems, e-mark'),
 ('fsa-additives.html','FSA-ADDITIVES',None,'Food Standards Agency','GB-ENG;GB-WLS;GB-NIR','glycerol slush drinks, dilution and portion guidance, E-number ingredient identity and GB/NI differences'),
 ('fsa-sfbb.pdf','FSA-SFBB-CATERERS','Safer food, better business for caterers — full pack','Food Standards Agency','UK; small catering businesses; use local jurisdiction checks','complete food safety management pack, safe methods, opening and closing checks, diary, supplier checks and reviews'),
]

def clean(text):
    return re.sub(r'\s+', ' ', text).strip()

def render(n, url, locators, figures):
    if isinstance(n, str):
        return re.sub(r'\s+', ' ', n)
    tag = n.tag
    if tag in {'script','style','nav','form','button','noscript'}:
        return ''
    if tag == 'img':
        figures.append({'alt':n.attrs.get('alt',''), 'source_url':urljoin(url,n.attrs.get('src','')), 'status':'linked_image_not_acquired'})
        return '\n\n[Normalization note: linked image not acquired; inspect original figure at '+figures[-1]['source_url']+']\n\n'
    if tag == 'ol':
        number=int(n.attrs.get('start','1'))
        items=[]
        for c in n.children:
            if isinstance(c,Node) and c.tag=='li':
                number=int(c.attrs.get('value',number))
                value=''.join(render(x,url,locators,figures) for x in c.children).strip()
                items.append(str(number)+'. '+value.replace('\n','\n   '))
                number+=1
        return '\n\n'+'\n\n'.join(items)+'\n\n'
    inner = ''.join(render(c,url,locators,figures) for c in n.children)
    if re.fullmatch(r'h[1-6]',tag):
        anchor=n.attrs.get('id')
        locator={'kind':'html_heading','heading':clean(n.text()),'origin_id':anchor,'source_url':url + ('#'+anchor if anchor else ''),'ordinal':len(locators)+1}
        locators.append(locator)
        return '\n\n' + '#'*int(tag[1]) + ' ' + inner.strip() + '\n\n' + '[Origin: '+locator['source_url']+']\n\n'
    if tag=='a' and n.attrs.get('href'):
        return '['+inner.strip()+']('+urljoin(url,n.attrs['href'])+')' if inner.strip() else ''
    if tag in {'strong','b'}: return '**'+inner.strip()+'**'
    if tag in {'em','i'}: return '*'+inner.strip()+'*'
    if tag=='br': return '\n'
    if tag=='li': return '\n- '+inner.strip()+'\n'
    if tag in {'table','thead','tbody','tfoot','tr','th','td','caption'}:
        attrs=''.join(' '+k+'="'+html.escape(v)+'"' for k,v in n.attrs.items() if k in {'rowspan','colspan','scope','id'})
        # HTML table markup retains span semantics that ordinary Markdown cannot express.
        return '\n<'+tag+attrs+'>'+inner.strip()+'</'+tag+'>\n'
    if tag in {'p','div','section','article','ul','ol','dl','dt','dd','blockquote','figure','figcaption'}:
        return '\n\n'+inner.strip()+'\n\n'
    if tag=='sup': return '<sup>'+inner.strip()+'</sup>'
    return inner

def main():
    logs=[json.loads(l) for l in (ROOT/'provenance/requests.jsonl').read_text(encoding='utf8').splitlines()]
    by_name={Path(r['path']).name:r for r in logs if 'path' in r}
    records=[]
    for index,(name,family,title,publisher,jurisdiction,topics) in enumerate(SELECTED,1):
        acq=by_name[name]
        path=ROOT/acq['path']
        raw=path.read_bytes()
        assert acq['http_status']==200 and acq['sha256']==sha(raw)
        locators,figures=[],[]
        date=None
        date_evidence=None
        extra={}
        if name.endswith('.pdf'):
            pdf=PdfReader(path)
            if family=='FSA-SFBB-CATERERS':
                extraction=json.loads((ROOT/'provenance/fsa-sfbb-page-text.json').read_text(encoding='utf8'))
                assert extraction['source_sha256']==sha(raw)
                pages=extraction['pages']
                extra['extractor']=extraction['extractor']
                extra['extractor_fallback_reason']=extraction['previous_extractor_error']
            else:
                pages=[p.extract_text() or '' for p in pdf.pages]
                extra['extractor']='Repository pypdf; page.extract_text; no OCR'
            assert len(pages)==len(pdf.pages) and sum(len(t) for t in pages)>1000,name
            sparse=[i for i,t in enumerate(pages,1) if len(t.strip())<350]
            body='\n\n'.join('## Original PDF page '+str(i)+'\n\n[Origin: '+acq['url']+'#page='+str(i)+']\n\n'+('[Normalization note: sparse embedded text on this page. Original may contain images, a section divider or form; no OCR was performed.]\n\n' if i in sparse else '')+text.strip() for i,text in enumerate(pages,1))
            locators=[{'kind':'pdf_page','page':i,'source_url':acq['url']+'#page='+str(i),'text_characters':len(t)} for i,t in enumerate(pages,1)]
            extra.update(page_count=len(pages),pdf_page_text_characters=[len(t) for t in pages],sparse_text_pages=sparse,parsing_status='embedded_text_extracted_all_pages_visual_content_not_transcribed',ocr_status='not_run',normalization_limitations=['Embedded text extracted from every PDF page. Images are not transcribed. PDF layout, diagrams, tables and reading order are authoritative in the original PDF; the text companion is not a visual facsimile.'])
            if family=='FSA-TRACEABILITY-RECALLS':
                extra['publication_date_text']='March 2019 (cover); day unknown'
                extra['image_text_missing_pages']=[53,54]
                extra['normalization_limitations'].append('PDF pages 53 and 54 are example recall/allergy posters stored as images, verified by rendering. Their text is absent from the companion. These are publisher examples, not active recalls.')
            elif family=='FSA-SFBB-CATERERS':
                extra['publication_date_text']='Exact date of this full-pack edition not confirmed; official landing page is separately preserved.'
            elif family=='HSE-CAIS26':
                extra['publication_date_text']='First published 2015 (last page); month/day unknown'
            else:
                extra['publication_date_text']='07/17 (publication footer); day unknown'
            if family=='HSE-CAIS24':
                extra['source_anomalies']=['Last-page footer prints CAIS23(rev3); first page, publisher landing page and PDF URL identify CAIS24. Preserved, not silently corrected.']
            extra['source_body_word_count']=len(' '.join(pages).split())
        else:
            tree=Tree(raw.decode('utf8')).root
            h1=tree.find(lambda n:n.tag=='h1')
            assert len(h1)==1,name
            title=clean(h1[0].text())
            bodies=tree.find(lambda n:'gem-c-govspeak' in n.attrs.get('class','').split())
            assert len(bodies)==1,name
            body=render(bodies[0],acq['url'],locators,figures)
            body=re.sub(r'\n[ \t]+','\n',body)
            body=re.sub(r'\n{3,}','\n\n',body).strip()
            metas={n.attrs.get('name'):n.attrs.get('content') for n in tree.find(lambda n:n.tag=='meta')}
            main_text=clean(tree.find(lambda n:n.tag=='main')[0].text())
            # Visible publication labels take precedence over migration metadata.
            match=re.search(r'Published:?\s+(\d{1,2} [A-Za-z]+ \d{4})',main_text)
            if match:
                from datetime import datetime
                date=datetime.strptime(match[1],'%d %B %Y').date().isoformat()
                date_evidence='Visible Published label: '+match[1]
            elif not name.startswith('fsa-') or name=='fsa-freezing.html':
                date=(metas.get('govuk:first-published-at') or '')[:10] or None
                date_evidence='govuk:first-published-at; may represent this GOV.UK publication, not original issuance'
            extra.update(publication_date_evidence=date_evidence,publisher_page_first_published_at=metas.get('govuk:first-published-at'),publisher_public_updated_at=metas.get('govuk:public-updated-at'),publisher_internal_updated_at=metas.get('govuk:updated-at'),source_body_word_count=len(bodies[0].text().split()),source_body_characters=len(bodies[0].text()),parsing_status='complete_main_publication_text_normalized',ocr_status='not_applicable',html_text_scope='The entire single gem-c-govspeak publication body; page furniture excluded.',linked_images=figures,normalization_limitations=['HTML document bytes saved; externally linked assets and attachments are not part of this acquisition. Images excluded from normalized text with explicit omission notes; captions and alt metadata retained. HTML tables retain row/column spans.'])
            assert extra['source_body_word_count']>=180,(name,extra['source_body_word_count'])
        stem='public-'+family.lower()
        norm=ROOT/'normalized'/(stem+'.md')
        locator_path=ROOT/'locators'/(stem+'.json')
        norm.parent.mkdir(exist_ok=True)
        locator_path.parent.mkdir(exist_ok=True)
        attribution=('Contains public sector information published by the Health and Safety Executive and licensed under the Open Government Licence.' if family.startswith('HSE-') else 'Contains public sector information licensed under the Open Government Licence v3.0.')
        header=f'# {title}\n\n> Acquisition metadata (not source prose). Publisher: {publisher}. Source family: {family}. Jurisdiction: {jurisdiction}.\n> Source: {acq["url"]}\n> Retrieved: {acq["retrieved_at"]}. Original-byte SHA-256: {acq["sha256"]}.\n> {attribution} Licence: {OGL}\n> Faithful format-normalized text, not a summary or translation. See manifest limitations and authoritative original for layout/figures.\n\n---\n\n'
        body=body.replace('\r\n','\n').replace('\r','\n')
        norm.write_text(header+body+'\n',encoding='utf8',newline='\n')
        locator_path.write_text(json.dumps(locators,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        terms=[by_name['terms-hse.html' if family.startswith('HSE-') else 'terms-govuk.html'],by_name['terms-ogl3.html']]
        record=dict(source_family_id=family,document_fixture_id=stem,version_fixture_id=stem+'-v1',title=title,publisher=publisher,url=acq['url'],source_url=acq['resolved_url'],language='en',jurisdiction=jurisdiction,publication_date=date,retrieved_at=acq['retrieved_at'],acquisition_status='acquired',use_terms_status='verified_ogl_v3_text_reuse_with_attribution',source_kind='public_guidance',original_path=path.relative_to(CORPUS).as_posix(),content_sha256=sha(raw),size_bytes=len(raw),mime='application/pdf' if name.endswith('.pdf') else 'text/html',synthetic=False,normalized_path=norm.relative_to(CORPUS).as_posix(),normalized_sha256=sha(norm.read_bytes()),normalized_size_bytes=norm.stat().st_size,normalized_mime='text/markdown',locator_path=locator_path.relative_to(CORPUS).as_posix(),locator_count=len(locators),acquisition_batch='pilot20' if index<=20 else 'expansion04',pilot_eligible=True,source_is_primary=True,source_scope='Public background guidance; no ShopSteward store adoption asserted',business_topics=topics,license_url=OGL,attribution=attribution,terms_evidence=[{'url':t['url'],'path':(ROOT/t['path']).relative_to(CORPUS).as_posix(),'sha256':t['sha256'],'retrieved_at':t['retrieved_at']} for t in terms],terms_conditions=['Attribute publisher and link OGL v3.0.','No endorsement implied. Logos and third-party rights excluded.','Use normalized text for cloud indexing; do not treat external image/asset URLs as acquired or licensed.','Raw PDFs retain integral logos and possibly third-party images for source verification; this record does not grant blanket image/logo republication rights.'],cloud_text_allowed=True,supersession={'status':'not_asserted','supersedes':[],'superseded_by':[],'note':'Acquisition is a dated snapshot, not proof of legal currency or store adoption.'},acquisition_http={'status':acq['http_status'],'redirects':acq['redirects'],'etag':acq['etag'],'last_modified':acq['last_modified']},**extra)
        records.append(record)
    assert len(records)==24
    assert len({r['content_sha256'] for r in records})==24
    (CORPUS/'public-sources.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf8',newline='\n')
    print(json.dumps({'acquired_documents':len(records),'original_bytes':sum(r['size_bytes'] for r in records),'normalized_bytes':sum(r['normalized_size_bytes'] for r in records),'source_words':sum(r['source_body_word_count'] for r in records),'pdf_pages':sum(r.get('page_count',0) for r in records)},indent=2))

if __name__=='__main__':
    main()
