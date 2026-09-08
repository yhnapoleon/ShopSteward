"""Append independently acquired expansion documents; never rebuild prior24.

Offline, deterministic text normalization. Run PDF extraction first with bundled
runtime; run this file with repository Python. No dependency installation.
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

sys.dont_write_bytecode=True
from acquire import ROOT,Tree,sha
from normalize import render,clean,OGL

CORPUS=ROOT.parent
EXP=ROOT/'expansion_20260908'
CC3='https://creativecommons.org/licenses/by/3.0/au/legalcode'
CC4='https://creativecommons.org/licenses/by/4.0/legalcode.en'
EPA='https://www.epa.gov/web-policies-and-procedures/epa-disclaimers'
FSANZ='Food Standards Australia New Zealand'
ACCC='Australian Competition and Consumer Commission'
HSE='Health and Safety Executive'
FSA='Food Standards Agency'
DEFRA='Department for Environment, Food & Rural Affairs'

# Family identity follows the complete publisher work or equipment-class guide.
# Titles inferred from HTML use the original h1, never generated source prose.
SELECTED=[
 ('es-ice-makers.html','EPA-ES-COMMERCIAL-ICE-MAKERS',None,'US EPA; ENERGY STAR','US','epa','Ice maker sizing, ice types, water and energy use; one complete equipment-class guide.'),
 ('es-dishwashers.html','EPA-ES-COMMERCIAL-DISHWASHERS',None,'US EPA; ENERGY STAR','US','epa','Commercial dishwasher classes, purchasing criteria and operating resource use.'),
 ('es-refrigeration.html','EPA-ES-COMMERCIAL-REFRIGERATION',None,'US EPA; ENERGY STAR','US','epa','Commercial reach-in refrigeration and freezer purchasing guidance; all models share one family.'),
 ('es-ovens.html','EPA-ES-COMMERCIAL-OVENS',None,'US EPA; ENERGY STAR','US','epa','Commercial oven types, sizing, cooking requirements and efficient operation.'),
 ('es-griddles.html','EPA-ES-COMMERCIAL-GRIDDLES',None,'US EPA; ENERGY STAR','US','epa','Griddle purchasing and cooking-surface energy performance.'),
 ('es-fryers.html','EPA-ES-COMMERCIAL-FRYERS',None,'US EPA; ENERGY STAR','US','epa','Commercial fryer selection and energy performance; independent from HSE hot-oil cleaning publication.'),
 ('es-steamers.html','EPA-ES-COMMERCIAL-STEAM-COOKERS',None,'US EPA; ENERGY STAR','US','epa','Steam cooker types, purchasing and water/energy performance.'),
 ('es-holding.html','EPA-ES-HOT-FOOD-HOLDING-CABINETS',None,'US EPA; ENERGY STAR','US','epa','Insulated hot-food holding cabinets and equipment purchasing criteria.'),
 ('es-coffee.html','EPA-ES-COMMERCIAL-COFFEE-BREWERS',None,'US EPA; ENERGY STAR','US','epa','Batch coffee brewer capacities, insulated tanks, auto-power-down and excluded machine classes; not an espresso service manual.'),
 ('es-cooktops.html','EPA-ES-COMMERCIAL-COOKTOPS',None,'US EPA; ENERGY STAR','US','epa','Commercial induction/electric cooktop purchasing and efficiency criteria.'),
 ('fsanz-safefood.pdf','FSANZ-SAFE-FOOD-AUSTRALIA','Safe Food Australia: A Guide to the Food Safety Standards — 4th edition, revised October 2024',FSANZ,'AU','fsanz3','Entire 278-page food-service standards manual; chapters, appendices and derivative Infobites are not extra families.'),
 ('fsanz-recall.pdf','FSANZ-FOOD-INDUSTRY-RECALL-PROTOCOL','Food Industry Food Recall Protocol — September 2024',FSANZ,'AU','fsanz-web','Entire food recall planning and execution protocol; no template or chapter counted separately.'),
 ('fsanz-npc.pdf','FSANZ-NUTRITION-PANEL-CALCULATOR-GUIDE','How to create a Nutrition Information Panel — Nutrition Panel Calculator User Guide 2026',FSANZ,'AU;NZ','fsanz4','Complete user guide for product nutrition panels; calculator, datasets and companion calculations are not extra documents.'),
 ('fsanz-allergens.html','FSANZ-ALLERGEN-LABELLING',None,FSANZ,'AU;NZ','fsanz-web','Standalone business guidance for mandatory allergen declarations and plain-English labelling.'),
 ('fsanz-claims.html','FSANZ-NUTRITION-HEALTH-CLAIMS',None,FSANZ,'AU;NZ','fsanz-web','Standalone guidance for nutrition content and health claims on food and beverage products.'),
 ('fsanz-pregnancy-design.html','FSANZ-ALCOHOL-PREGNANCY-LABELS',None,FSANZ,'AU;NZ','fsanz-web','Complete design and FAQ guidance for alcohol pregnancy warning labels; overview, label variants and downloadable artwork share this family.'),
 ('accc-origin.pdf','ACCC-COUNTRY-OF-ORIGIN-FOOD-LABELLING','Country of Origin food labelling — A guide for business, current as of March 2021',ACCC,'AU','accc3','Complete food country-of-origin labelling guide, including packaged and unpackaged grocery products.'),
 ('accc-unit-pricing.pdf','ACCC-GROCERY-UNIT-PRICING','Unit pricing — A guide for grocery retailers, October 2021',ACCC,'AU','accc3','Complete grocery shelf, online and promotional unit-pricing guide.'),
 ('accc-green-claims.pdf','ACCC-ENVIRONMENTAL-CLAIMS','Making environmental claims — A guide for business, December 2023',ACCC,'AU','accc4','Complete product and packaging environmental-claims guide; useful for recyclable, compostable and sustainability claims.'),
 ('uk-fire-shops.html','HOME-OFFICE-FIRE-OFFICES-SHOPS',None,'Home Office','GB-ENG','ogl','Entire offices-and-shops fire-risk-assessment manual, including evacuation, escape routes, alarms and records; no chapter splitting.'),
 ('uk-vacuum.pdf','FSA-VACUUM-MAP-SHELF-LIFE','The safety and shelf-life of vacuum and modified atmosphere packed chilled foods with respect to non-proteolytic Clostridium botulinum',FSA,'UK; see source scope','ogl','Complete vacuum/MAP chilled-food safety and shelf-life technical guide; overview and additional Q&A are not extra families.'),
 ('uk-burgers.pdf','FSA-LTTC-BEEF-BURGERS','Less than thoroughly cooked beef burgers: guidance for food businesses',FSA,'GB-ENG;GB-WLS;GB-NIR','ogl','Complete specialist catering burger guide; source-control diagram and underpinning studies do not add families.'),
 ('uk-ecoli.pdf','FSA-ECOLI-CROSS-CONTAMINATION','E. coli O157: Control of Cross-contamination — Guidance for food business operators and local authorities, 2019',FSA,'GB-ENG;GB-WLS;GB-NIR','ogl','Complete technical guidance for raw/ready-to-eat separation, complex equipment and disinfection; linked caterer factsheet not counted.'),
 ('uk-bags.html','DEFRA-CARRIER-BAG-CHARGES',None,DEFRA,'GB-ENG','ogl','Checkout carrier-bag charging, exceptions and reporting obligations.'),
 ('uk-drs.html','DEFRA-DRINKS-DEPOSIT-RETURN',None,DEFRA,'GB-ENG;GB-NIR; see source for other nations','ogl','Drinks container deposit/return-point responsibilities; future scheme preparation, not a claim that requirements are already in force.'),
 ('uk-alcohol.html','HOME-OFFICE-ALCOHOL-LICENSING',None,'Home Office','GB-ENG;GB-WLS','ogl','Alcohol premises and personal licensing, designated supervisors, supply chain and licence variations.'),
 ('uk-recycling.html','DEFRA-WORKPLACE-RECYCLING',None,DEFRA,'GB-ENG','ogl','Separation and collection of workplace food/recyclable waste, micro-firm deadlines and waste containers.'),
 ('uk-composition.html','DEFRA-FOOD-COMPOSITION-STANDARDS',None,DEFRA,'GB-ENG','ogl','One complete product-composition guide covering coffee, juices, honey, chocolate and other reserved product descriptions; product sections do not add families.'),
 ('uk-water.html','DEFRA-BOTTLED-DRINKING-WATER',None,DEFRA,'GB-ENG','ogl','Bottled drinking-water product definition, treatment and label requirements. No mineral/spring-water variants counted separately.'),
 ('uk-returns.html','GOVUK-RETURNS-REFUNDS',None,'GOV.UK','UK','ogl','Shop returns, refunds, proof of purchase, faulty goods and perishable-product exceptions.'),
 ('uk-spirits.html','DEFRA-SPIRIT-DRINK-LABELLING',None,DEFRA,'UK; distinct GB and NI rules','ogl','Spirit drink names, allusions, compound terms and low/non-alcohol products; product-specific guide, not a general-label chapter.'),
 ('uk-tips.html','DBT-FAIR-TIPS-CODE',None,'Department for Business and Trade','GB','ogl','Complete published tipping code, allocation, records and staff transparency; 2026 draft revision is not a second family or adopted rule.'),
 ('hse-cais25.pdf','HSE-CAIS25','Managing risk in catering and hospitality: Your responsibilities',HSE,'GB','hse','Published catering risk-management duties, assessment and responsibilities; independent complete CAIS25 publication.'),
 ('hse-checkout-canonical.pdf','HSE-INDG269','Managing musculoskeletal disorders in checkout work: A brief guide',HSE,'GB','hse','Complete checkout workstation and checkout task ergonomics guide, distinct from catering manual handling.'),
 ('hse-electrical-canonical.pdf','HSE-INDG236','Maintaining portable electric equipment in low-risk environments',HSE,'GB','hse','Complete low-risk shop electrical-equipment checking guide. Does not cover harsh/wet commercial kitchen environments by default.'),
 ('hse-knives.html','HSE-KITCHEN-KNIFE-SAFETY',None,HSE,'GB','hse','Complete kitchen knife task and storage safety guidance.'),
 ('hse-skin.html','HSE-CATERING-SKIN-PROTECTION',None,HSE,'GB','hse','Complete catering dermatitis prevention, wet-work controls, glove selection and skin checks.'),
 ('phe-catering.pdf','PHE-HEALTHIER-SUSTAINABLE-CATERING','Healthier and more sustainable catering: A toolkit for serving food to adults','Public Health England','GB-ENG','ogl','Entire 86-page adult catering toolkit: menu planning, healthier ingredients and food purchasing. Related checklist and sector adaptations are not extra families.'),
 ('accc-advertising.pdf','ACCC-ADVERTISING-SELLING','Advertising and selling guide — A guide for business, July 2021',ACCC,'AU','accc3','Complete guide for retail advertising, promotional offers, selling practices and product claims; its individual topics are not extra families.'),
 ('acl-guarantees.pdf','ACL-CONSUMER-GUARANTEES','Consumer guarantees — A guide for businesses and legal practitioners, March 2016','Australian Consumer Law regulators; Commonwealth of Australia','AU','accc3','Complete joint primary regulator guide to retail product/service guarantees and remedies, not the consumer-summary variant.'),
 ('cma-pricing.pdf','CMA209-PRICE-TRANSPARENCY','Unfair commercial practices: price transparency — CMA209','Competition and Markets Authority','UK','ogl','Complete 58-page price transparency guide, covering unavoidable charges, delivery fees, drip pricing and partitioned pricing. Summary, webinars and revisions are one family.'),
 ('fss-retailsafe.pdf','FSS-RETAILSAFE','RetailSafe — Food Safety Assurance System for Retailers Handling Unwrapped High Risk Food','Food Standards Scotland','GB-SCT','fss','Complete 96-page retail food safety manual. CookSafe-derived approach, house rules, templates, translations and sector variants do not add families in this batch.'),
]

# Explicit user steering: exclude ambiguous licence notices, rather than resolve
# conflicts by assumption. Original downloads remain quarantined audit evidence.
HELD_LICENCE_TYPES={'fsanz-web','fsanz4','accc4'}

def terms_record(r,old=False):
    path=(ROOT/r['path'] if old else CORPUS/r['path'])
    assert sha(path.read_bytes())==r['sha256']
    return {'url':r['url'],'path':path.relative_to(CORPUS).as_posix(),'sha256':r['sha256'],'retrieved_at':r['retrieved_at']}

def main():
    manifest=CORPUS/'public-sources.jsonl'
    lock=json.loads((ROOT/'provenance/prior24-stability-lock.json').read_text(encoding='utf8'))
    prior=manifest.read_bytes()
    assert sha(prior[:lock['manifest_bytes']])==lock['manifest_sha256']
    assert [json.loads(l) for l in prior.decode('utf8').splitlines()][:24]==lock['records']
    already={json.loads(l)['source_family_id'] for l in prior.decode('utf8').splitlines()}
    oldlogs=[json.loads(l) for l in (ROOT/'provenance/requests.jsonl').read_text(encoding='utf8').splitlines()]
    newlogs=[json.loads(l) for l in (EXP/'requests.jsonl').read_text(encoding='utf8').splitlines()]
    byname={Path(r['path']).name:r for r in newlogs if r.get('path')}
    oldname={Path(r['path']).name:r for r in oldlogs if r.get('path')}
    records=[]
    for name,family,title,publisher,jurisdiction,lic,topics in SELECTED:
        if lic in HELD_LICENCE_TYPES:continue
        if family in already:continue
        acq=byname[name]; path=CORPUS/acq['path']; raw=path.read_bytes()
        assert acq['http_status']==200 and len(raw)>1000 and sha(raw)==acq['sha256']
        locators=[];figures=[];extra={}; date=None
        if name.endswith('.pdf'):
            assert raw.startswith(b'%PDF-')
            extraction=EXP/'extracted'/(Path(name).stem+'.json')
            d=json.loads(extraction.read_text(encoding='utf8'))
            assert d['source_sha256']==sha(raw)
            pages=d['pages']; assert len(pages)>0 and sum(map(len,pages))>1000
            sparse=[i for i,t in enumerate(pages,1) if len(t.strip())<350]
            irregular=[i for i,t in enumerate(pages,1) if any(c in t for c in ['\ufffd','\ufffe','\x02'])]
            body='\n\n'.join('## Original PDF page '+str(i)+'\n\n[Origin: '+acq['url']+'#page='+str(i)+']\n\n'+('[Normalization note: sparse embedded text; inspect original page. No OCR.]\n\n' if i in sparse else '')+t.strip() for i,t in enumerate(pages,1))
            locators=[{'kind':'pdf_page','page':i,'source_url':acq['url']+'#page='+str(i),'text_characters':len(t)} for i,t in enumerate(pages,1)]
            extra.update(page_count=len(pages),pdf_page_text_characters=[len(t) for t in pages],sparse_text_pages=sparse,irregular_glyph_pages=irregular,extractor=d['extractor'],extraction_path=extraction.relative_to(CORPUS).as_posix(),extraction_sha256=sha(extraction.read_bytes()),parsing_status='all_pages_embedded_text_extracted_visual_content_partial',normalized_text_coverage='embedded_text_only_no_OCR',ocr_status='not_run',source_body_word_count=len(' '.join(pages).split()),publication_date_evidence='No exact original publication day confirmed. Edition/month/year retained in title or source text; URL upload dates are not publication dates.',normalization_limitations=['All original PDF pages acquired and all pages processed. Diagrams, pictures, image text, table geometry and reading order are not fully represented in Markdown.','Sparse pages may be covers, figures or blank forms. Do not infer their missing content.','Unusual extraction glyphs are retained rather than silently inventing missing words. Consult the original PDF.'])
        else:
            tree=Tree(raw.decode('utf8')).root
            h1=tree.find(lambda n:n.tag=='h1'); assert len(h1)==1,name
            title=clean(h1[0].text())
            if 'gov.uk' in acq['resolved_url'] and not 'hse.gov.uk' in acq['resolved_url']:
                bodies=tree.find(lambda n:'gem-c-govspeak' in n.attrs.get('class','').split())
                scope='entire single gem-c-govspeak publication body'
            elif lic.startswith('fsanz'):
                bodies=tree.find(lambda n:n.tag=='article' and 'basic-page' in n.attrs.get('class','').split())
                scope='entire outer basic-page article, selected once; nested article is not duplicated'
            else:
                bodies=tree.find(lambda n:n.tag=='main')
                scope='entire main element; scripts, styles, forms and navigation removed; remaining related-publication links retained'
            assert len(bodies)==1,(name,len(bodies))
            body=render(bodies[0],acq['url'],locators,figures)
            body=re.sub(r'\n[ \t]+','\n',body)
            body=re.sub(r'\n{3,}','\n\n',body).strip()
            if not locators:locators=[{'kind':'html_publication','heading':title,'source_url':acq['url'],'ordinal':1}]
            metas={n.attrs.get('name'):n.attrs.get('content') for n in tree.find(lambda n:n.tag=='meta')}
            main=tree.find(lambda n:n.tag=='main')
            match=re.search(r'Published:?\s+(\d{1,2} [A-Za-z]+ \d{4})',clean(main[0].text())) if main and lic=='ogl' else None
            if match:date=datetime.strptime(match[1],'%d %B %Y').date().isoformat()
            extra.update(publication_date_evidence='Visible Published label: '+match[1] if match else 'Exact original publication day not confirmed; not inferred from retrieval or upload dates.',publisher_page_first_published_at=metas.get('govuk:first-published-at'),publisher_public_updated_at=metas.get('govuk:public-updated-at'),source_body_word_count=len(bodies[0].text().split()),source_body_characters=len(bodies[0].text()),parsing_status='complete_selected_main_text_normalized_external_assets_not_acquired',normalized_text_coverage='selected_full_publication_body',ocr_status='not_applicable',html_text_scope=scope,linked_images=figures,normalization_limitations=['Complete HTML response acquired, not its external images, attachments, scripts or interactive databases.','Source headings, links, tables and lists are normalized from the complete selected publication body. No summary, translation or generated operational advice.','External images have explicit omission markers and origin URLs; captions remain. Diagram-dependent answers require the source.'])
            assert extra['source_body_word_count']>=200,(name,extra['source_body_word_count'])
        terms=[];conditions=[];notes=[]
        if lic in ['ogl','hse','fss']:
            license_url=OGL; status='verified_ogl_v3_text_reuse_with_attribution'
            terms=[terms_record(oldname['terms-hse.html' if lic=='hse' else 'terms-govuk.html'],True),terms_record(oldname['terms-ogl3.html'],True)]
            if lic=='fss':terms=[terms_record(byname['fss.html']),terms_record(oldname['terms-ogl3.html'],True)]
            attribution='Contains public sector information '+('published by the Health and Safety Executive and ' if lic=='hse' else '')+'licensed under the Open Government Licence v3.0.'
        elif lic=='epa':
            license_url=EPA;status='verified_noncommercial_scientific_educational_use_only'
            terms=[terms_record(byname['epa.html']),terms_record(byname['energystar.html'])]
            attribution='Source: U.S. Environmental Protection Agency, ENERGY STAR. Reproduced for noncommercial scientific/educational evaluation; no endorsement implied.'
            conditions+=['EPA notice permits free use/distribution for noncommercial scientific and educational purposes. This acquisition relies only on that purpose.','Commercial reuse is not cleared by this record. Do not promote this pilot permission to unrestricted production or commercial use.']
        else:
            license_url=CC3 if lic.endswith('3') else CC4
            status='verified_cc_by_3_au_text_reuse_with_attribution' if lic.endswith('3') else 'verified_cc_by_4_text_reuse_with_attribution'
            attribution=('© Food Standards Australia New Zealand.' if lic.startswith('fsanz') else '© Australian Competition and Consumer Commission / Commonwealth of Australia; see original copyright year.')
            if lic.startswith('fsanz'):terms.append(terms_record(byname['fsanz.html']))
            if name.endswith('.pdf'):
                terms.append({'url':acq['url'],'path':acq['path'],'sha256':sha(raw),'retrieved_at':acq['retrieved_at'],'evidence_locator':'PDF copyright statement; inspect page 2 for NPC/ACCC pricing/claims, page 3 for Safe Food Australia, final page for ACCC origin. Recall PDF uses publisher website notice.'})
            terms.append(terms_record(byname['cc-by3-au.html' if lic.endswith('3') else 'cc-by4.html']))
            conditions+=['Attribute the publisher, link the licence and source, retain notices, identify format normalization, and imply no endorsement.']
            if lic=='fsanz-web':
                status='verified_cc_by_text_reuse_version_notice_conflict_retained'
                terms.append(terms_record(byname['cc-by3-au.html']))
                notes+=['FSANZ site notice says CC BY 4.0 but its licence hyperlink points to CC BY 3.0 Australia and includes a CC BY43.0 typo. Both allow attributed text reuse; comply with both notices conservatively. No silent assertion that the conflicting version label is resolved.']
            if lic.endswith('4'):notes+=['The PDF copyright wording, where applicable, says CC BY 4.0 Australia. CC BY 4.0 legal code is International; the publisher geographic wording is preserved, not silently treated as a separate ported licence.']
            if lic.startswith('accc'):conditions+=['Publisher requests currency/accuracy review before each republication. Dated research snapshot, not a representation of current Australian legal requirements.']
        conditions+=['Logos, trademarks, third-party images and externally linked content are not granted blanket reuse rights.','Use normalized first-party text for the authorized background pilot subject to this record’s purpose restrictions. No automatic HK/store policy adoption.','Integral visual content is retained only within original downloaded bytes for verification. Normalized text is not a full visual substitute.']
        if family=='ACCC-ENVIRONMENTAL-CLAIMS':notes+=['Official publication landing page warns that this December 2023 PDF does not reflect penalty increases effective 28 March 2026. Do not use its penalty amounts as current law.']
        if family=='DBT-FAIR-TIPS-CODE':notes+=['A revised code was published for consultation in 2026. This is the published 2024 code snapshot; draft and final are one family. No claim of legal currency or draft adoption.']
        if family=='FSA-ECOLI-CROSS-CONTAMINATION':notes+=['Original PDF cover says 2019; GOV.UK wrapper says published 23 January 2024 and uploaded URL is newer. Original edition retained.']
        if family=='HSE-INDG236':notes+=['Scope explicitly low-risk settings such as shops/offices; inspection intervals must not be applied automatically to wet/harsh food-production areas.']
        if family=='EPA-ES-COMMERCIAL-COFFEE-BREWERS':notes+=['Source contains both 27 percent and about 30 percent energy-efficiency statements. Preserved without harmonization; espresso/bean-to-cup machines excluded by source.']
        stem='public-'+family.lower();norm=EXP/'normalized'/(stem+'.md');lp=EXP/'locators'/(stem+'.json')
        norm.parent.mkdir(exist_ok=True);lp.parent.mkdir(exist_ok=True)
        header=f'# {title}\n\n> Acquisition metadata, not source prose. Publisher: {publisher}. Family: {family}. Jurisdiction: {jurisdiction}.\n> Source: {acq["url"]}\n> Retrieved: {acq["retrieved_at"]}. Original-byte SHA-256: {sha(raw)}.\n> {attribution} Licence/terms: {license_url}\n> Faithful format normalization; no translation or summary. Original bytes remain authoritative for figures, layout and scope.\n> '+('Noncommercial scientific/educational pilot use only; commercial use not cleared.\n> ' if lic=='epa' else '')+'Public background evidence only. No automatic Hong Kong or store adoption.\n\n'
        if notes:header+='> Acquisition notes: '+' '.join(notes)+'\n\n'
        norm.write_text(header+'---\n\n'+body.replace('\r\n','\n').replace('\r','\n')+'\n',encoding='utf8',newline='\n')
        lp.write_text(json.dumps(locators,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
        r=dict(source_family_id=family,document_fixture_id=stem,version_fixture_id=stem+'-v1',title=title,publisher=publisher,url=acq['url'],source_url=acq['resolved_url'],language='en',jurisdiction=jurisdiction,publication_date=date,retrieved_at=acq['retrieved_at'],acquisition_status='acquired',use_terms_status=status,source_kind='public_guidance',original_path=acq['path'],content_sha256=sha(raw),size_bytes=len(raw),mime='application/pdf' if name.endswith('.pdf') else 'text/html',synthetic=False,original_complete=True,normalized_path=norm.relative_to(CORPUS).as_posix(),normalized_sha256=sha(norm.read_bytes()),normalized_size_bytes=norm.stat().st_size,normalized_mime='text/markdown',locator_path=lp.relative_to(CORPUS).as_posix(),locator_sha256=sha(lp.read_bytes()),locator_count=len(locators),acquisition_batch='expansion20260908-01',pilot_eligible=True,source_is_primary=True,source_scope='Public background guidance; no HK or ShopSteward store adoption asserted',business_topics=topics,source_family_rationale=topics,counting_rule='One independent complete publisher work; no translations, mirrors, revisions, models, chapters or supplementary slices counted again.',license_url=license_url,attribution=attribution,terms_evidence=terms,terms_conditions=conditions,terms_notes=notes,cloud_text_allowed=True,cloud_use_scope='noncommercial_scientific_educational_pilot_only' if lic=='epa' else 'attributed_first_party_background_text_subject_to_terms',commercial_use_status='not_cleared' if lic=='epa' else 'permitted_for_licensed_text_subject_to_terms',automatic_store_adoption=False,automatic_hk_adoption=False,requires_original_for_visual_content=True,supersession={'status':'not_asserted','supersedes':[],'superseded_by':[],'note':'Dated snapshot, not proof of legal currency, adoption or supersession.'},acquisition_http={k:acq.get(k) for k in ['http_status','redirects','etag','last_modified']},**extra)
        records.append(r)
    assert len({r['source_family_id'] for r in records})==len(records)
    assert all(r['source_family_id'] not in already for r in records)
    # Validate every new record before the single append; prior bytes stay exact.
    for r in records:
        assert sha((CORPUS/r['original_path']).read_bytes())==r['content_sha256']
        assert sha((CORPUS/r['normalized_path']).read_bytes())==r['normalized_sha256']
    staged=EXP/'direct-records.staged.jsonl'
    staged.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf8',newline='\n')
    if records and '--publish' in sys.argv:
        assert manifest.read_bytes()==prior,'Concurrent manifest change; no append attempted'
        with manifest.open('ab') as f:f.write(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records).encode('utf8'))
    assert manifest.read_bytes()[:len(prior)]==prior
    print(json.dumps({'staged':len(records),'appended':len(records) if '--publish' in sys.argv else 0,'total_if_admitted':len(already)+len(records),'new_original_bytes':sum(r['size_bytes'] for r in records),'new_source_words':sum(r['source_body_word_count'] for r in records)},indent=2))

if __name__=='__main__':main()
