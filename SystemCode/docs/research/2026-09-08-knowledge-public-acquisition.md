# Public-source acquisition for the precloud pilot

Acquired on 2026-09-08 Asia/Shanghai (HTTP timestamps are 2026-09-07 UTC). Scope: the assigned public corpus, its source manifest, and this report. Read the [source catalog](2026-09-07-knowledge-public-source-catalog.md) and [corpus design](../superpowers/specs/2026-09-07-cloud-knowledge-and-corpus-design.md).

## Delivered state

**24 independently published source families acquired: 20 pilot documents plus 4 expansion documents.** These are 10 complete PDF files (193 pages) and 14 complete HTML publication responses, accompanied by 24 faithful format-normalized Markdown text files. They are official operational guidance, not link collections or model-written substitutes. Exact downloaded bytes total **12,684,550**; normalized text totals **941,572 bytes** and approximately **117,107 source words** (whitespace count, including PDF headers/forms). HTML external images/assets and linked attachments are not included in the acquired response bytes.

The first 20 records remain `acquisition_batch=pilot20`; the 4 additions use `expansion04`. The first batch alone has 9 PDFs / 93 pages and 11 HTML publications, 4,461,420 original bytes and approximately 81,194 source words. There are zero hash duplicates, and each translation/alternate format/handbook family is counted once. No public documents have been loaded into the application, cloud index or embedding service by this work.

**Remaining gap to 100 public documents: 76.** This is an honest first-batch handoff, not a claim that 100 suitable sources are impossible to obtain. Expansion in this run was limited to four identified, obtainable sources that add pricing, package quantities, drink additives and a complete catering management pack. All 24 are English-language UK/Great Britain guidance with explicit country scopes. Manufacturer/model-specific manuals acquired: **0**. HK/Chinese originals acquired: **0**. Supplier contracts, actual store events and SKU compatibility remain uncovered by these public originals. Filling the remaining quota requires further independent, rights-cleared acquisition; none of the remaining 76 is represented by placeholder originals.

## Corpus-agent contract

[public-sources.jsonl](../evaluation/knowledge-expanded/public-sources.jsonl) contains **acquired documents only**, using Singer's requested fields:

`source_family_id`, `document_fixture_id`, `version_fixture_id`, `title`, `publisher`, `url`, `source_url`, `language`, `jurisdiction`, nullable `publication_date`, `retrieved_at`, `acquisition_status`, `use_terms_status`, `source_kind`, `original_path`, `content_sha256`, `size_bytes`, `mime`, `synthetic=false`.

- All paths in manifest records are relative to `docs/evaluation/knowledge-expanded/`. `original_path` is the actual downloaded PDF or HTML response; its exact bytes match `content_sha256` and `size_bytes`.
- For the public **text** ingestion path, consume `normalized_path` with `normalized_sha256`, `normalized_size_bytes` and `normalized_mime=text/markdown`. Do not attach the original-byte hash to normalized bytes. Original and normalized representations are the **same document/version**, not two documents. Stable IDs use `public-<source-family-lowercase>` and `-v1`.
- Extra fields provide `locator_path`, `locator_count`, topics, verified terms URLs/snapshot hashes, attribution, HTTP response metadata, parsing/OCR limitations, publisher timestamps, supersession status and batch. `pilot_eligible=true` indicates this acquisition gate; it does not assert that every pixel was OCRed or that application import/evaluation passed.
- `source_kind=public_guidance`, `acquisition_status=acquired`, `use_terms_status=verified_ogl_v3_text_reuse_with_attribution`, `cloud_text_allowed=true`. Public-sector guidance is background evidence; no ShopSteward store adoption, effective date, or live recall is asserted.
- Keep the `pilot20` filter if the aggregate pilot needs exactly 20 public documents. The four `expansion04` additions are optional for that aggregate, but are real acquired documents toward the larger quota. Aggregate schema/manifests and synthetic files were left to Singer.

## Source inventory and original-byte hashes

Each row is one independently published logical document. Word counts describe the source body/embedded PDF text, not an assistant summary. PDF page counts use physical file pages, so publisher-printed page numbers can differ.

| Family / batch | Official original | Format / pages | Source words | Original bytes | SHA-256 of original bytes |
|---|---|---|---:|---:|---|
| HSE-CAIS17 / pilot20 | [Safety during emptying and cleaning of fryers](https://www.hse.gov.uk/pubns/cais17.pdf) | PDF / 4 | 1,802 | 184,558 | `a48909993dc7a08592473ef02b4245391a7710c6c25f1ee5329d4e215f3b02c4` |
| HSE-CAIS6 / pilot20 | [Preventing slips and trips in kitchens and food service](https://www.hse.gov.uk/pubns/cais6.pdf) | PDF / 4 | 2,251 | 309,252 | `db66d09ac447fe899075990d1cb18d11227f9204c6aeb543efc21fc78e850055` |
| HSE-CAIS10 / pilot20 | [Ventilation in catering kitchens](https://www.hse.gov.uk/pubns/cais10.pdf) | PDF / 4 | 2,110 | 175,567 | `5d9b2252a4b42ee36ff9bb9f6f4f2718f15b92b1a68f8c1eba9d8b3c37abe19c` |
| HSE-CAIS12 / pilot20 | [Maintenance priorities in catering](https://www.hse.gov.uk/pubns/cais12.pdf) | PDF / 5 | 1,732 | 168,682 | `9d1abf9b85e9219dc9975d2b24da5fe216854787dc1429dc1e1a62ba416f9211` |
| HSE-CAIS22 / pilot20 | [Safe use of cleaning substances in the hospitality industry](https://www.hse.gov.uk/pubns/cais22.pdf) | PDF / 4 | 1,968 | 164,511 | `cc8e55274d565b10ecc57430faf686fc6cf9107e19232322a1b9c5dfd08d53e1` |
| HSE-CAIS23 / pilot20 | [Gas safety in catering and hospitality](https://www.hse.gov.uk/pubns/cais23.pdf) | PDF / 6 | 3,040 | 216,639 | `070e0520865520d877d825630c3706875d24ab5d73d91786bfc17ae0c7cad848` |
| HSE-CAIS24 / pilot20 | [Preventing manual handling injuries to catering staff](https://www.hse.gov.uk/pubns/cais24.pdf) | PDF / 6 | 2,889 | 221,211 | `22665185a22a4aaacb53a98c285c61dec0e35554d27dd2f3fd67dcf50c2dd111` |
| HSE-CAIS26 / pilot20 | [Preventing exposure to carbon monoxide from use of solid fuel appliances in commercial kitchens](https://www.hse.gov.uk/pubns/cais26.pdf) | PDF / 4 | 2,324 | 115,380 | `51a6272b9004e5d3a0d032464b901336a9d578bfcbcc958c7c84ac0d44e225ab` |
| FSA-BULK-FREEZING / pilot20 | [Bulk freezing of ambient and chilled foods](https://www.gov.uk/government/publications/bulk-freezing-of-ambient-and-chilled-foods/bulk-freezing-of-ambient-and-chilled-foods) | HTML | 1,208 | 86,122 | `78b7c8994ef945ee4911ac2056ce9a7454310fe8024c7ee293ecd95b7a552160` |
| FSA-FOOD-DELIVERY / pilot20 | [Food safety for food delivery](https://www.gov.uk/government/publications/food-safety-for-food-delivery/food-safety-for-food-delivery) | HTML | 931 | 84,064 | `266180f56ee04c2707d78a5c2cf357fb53fffe8c2074ea51130cc6f6dfc35d51` |
| FSA-ALLERGEN-TECHNICAL / pilot20 | [Food allergen labelling and information requirements technical guidance](https://www.gov.uk/government/publications/food-allergen-labelling-and-information-requirements-technical-guidance/food-allergen-labelling-and-information-requirements-technical-guidance) | HTML | 10,421 | 276,275 | `3c8c8f084bc4e2940856f3465ac2ba288ec42ce588c970bf643348cce7ce8122` |
| FSA-FOOD-CONTACT-REGULATIONS / pilot20 | [Food contact materials regulations](https://www.gov.uk/government/publications/food-contact-materials-regulations/food-contact-materials-regulations) | HTML | 220 | 66,313 | `e1c3085e832b65ceb25bca5388e40371433066501f6aaccd7d445ba8a5200ce1` |
| FSA-BIOBASED-FCM / pilot20 | [Biobased FCM: A Starter’s Guide For The Development Of New Biobased Food Contact Materials](https://www.gov.uk/guidance/biobased-fcm-a-starters-guide-for-the-development-of-new-biobased-food-contact-materials) | HTML | 4,522 | 141,711 | `c799f9f47be12c4e264e49b4256c76d75c9028d8a1d352bd7572aaa4920a7953` |
| DEFRA-FOOD-INFORMATION / pilot20 | [Food labelling: giving food information to consumers](https://www.gov.uk/guidance/food-labelling-giving-food-information-to-consumers) | HTML | 3,105 | 137,536 | `c63d05573d9bf136d39466c29ba6190e4c5df05d6cfbda6d067a83a7b3a94ddc` |
| FSA-ACRYLAMIDE / pilot20 | [Acrylamide legislation](https://www.gov.uk/government/publications/acrylamide-legislation/acrylamide-legislation) | HTML | 755 | 74,880 | `786674054980fb16917b31705fadad7eaf822ffab42644d495febcc6cf6c5577` |
| DEFRA-SINGLE-USE-PLASTICS / pilot20 | [Single-use plastics bans and restrictions](https://www.gov.uk/guidance/single-use-plastics-bans-and-restrictions) | HTML | 1,146 | 98,435 | `00a78bb47f21da2aaf82e92b7256e6690c66ce6ca6ec1e9547f07ad5cef7b035` |
| DEFRA-FOOD-WASTE-HIERARCHY / pilot20 | [Food and drink waste hierarchy: deal with surplus and waste](https://www.gov.uk/government/publications/food-and-drink-waste-hierarchy-deal-with-surplus-and-waste/food-and-drink-waste-hierarchy-deal-with-surplus-and-waste) | HTML | 1,898 | 114,555 | `1c84a34936621a34b5138e8f197fe32c11b7c7b6ac3bb116b241ad3878addb0e` |
| DHSC-CALORIE-LABELLING / pilot20 | [Calorie labelling in the out of home sector: implementation guidance](https://www.gov.uk/government/publications/calorie-labelling-in-the-out-of-home-sector/calorie-labelling-in-the-out-of-home-sector-implementation-guidance) | HTML | 6,313 | 171,278 | `ef2073f6aee82a9d6ce27bd882ba28cc019b8092a192892dff8a5bb073ce9179` |
| DHSC-HFSS-PROMOTIONS / pilot20 | [Restricting promotions of products high in fat, sugar or salt by location and by volume price: implementation guidance](https://www.gov.uk/government/publications/restricting-promotions-of-products-high-in-fat-sugar-or-salt-by-location-and-by-volume-price/restricting-promotions-of-products-high-in-fat-sugar-or-salt-by-location-and-by-volume-price-implementation-guidance) | HTML | 19,512 | 416,723 | `3e0b50b1f232dd2d13965f05e51d2bc11852918246362d34c4ea552388a951b2` |
| FSA-TRACEABILITY-RECALLS / pilot20 | [Guidance on Food Traceability, Withdrawals and Recalls within the UK Food Industry](https://assets.publishing.service.gov.uk/media/69fc4f404fb0713aa63ea57e/food-traceability-withdrawals-and-recalls-guidance.pdf) | PDF / 56 | 13,047 | 1,237,728 | `614d6f7b606129c04df14780efa01a42e4df2ca704f2d95acfee160717c56970` |
| DBT-PRICE-MARKING / expansion04 | [Price Marking Order 2004: government guidance](https://www.gov.uk/government/publications/price-marking-order-2004-government-guidance/price-marking-order-2004-government-guidance) | HTML | 5,408 | 149,499 | `ff32583165d14f2086d57536686c4cbe0631a3c9569a59a42ea1b26696bbd12f` |
| OPSS-PACKAGED-GOODS / expansion04 | [Packaged goods: weights and measures regulations](https://www.gov.uk/guidance/packaged-goods-weights-and-measures-regulations) | HTML | 718 | 95,588 | `414dde6a1bc3116aac41cecd2d29a7c8a68170d4dfb6b7a9411720e1f4253314` |
| FSA-ADDITIVES / expansion04 | [Approved additives and E numbers](https://www.gov.uk/government/publications/approved-additives-and-e-numbers/approved-additives-and-e-numbers) | HTML | 1,846 | 153,173 | `92cb523b519d151da23fb99897e0a8925d575a49a64d00ab2fb8590e21ba0a61` |
| FSA-SFBB-CATERERS / expansion04 | [Safer food, better business for caterers — full pack](https://assets.publishing.service.gov.uk/media/69c5247ecdfd19de13d0f6ca/sfbb-caterers-pack-fixed_0_3.pdf) | PDF / 100 | 27,941 | 7,824,870 | `35b2eea9a33741cca907e0902847ca003fabc792bb4149216987102441952838` |

The HSE CAIS publications form a series, but each has its own title, complete standalone publication and decision scope. They are not chapter slices of a downloaded manual. The complete SFBB caterers pack counts once; its separately published chapter PDFs and translated/adapted packs were not counted. Recall guidance and its quick-reference sheet/poster examples count as one family; only the complete main PDF counts. The allergen technical guidance, general food-information guidance, food-contact regulation overview and biobased-materials guide are separate documents with different purposes, not mirrors of each other. The food-contact overview is a genuinely short 220-word official publication; its complete body is preserved and is not a fabricated summary.

## Actual usage terms and provenance

For accepted documents, [GOV.UK terms](https://www.gov.uk/help/terms-conditions), [HSE copyright terms](https://www.hse.gov.uk/help/copyright.htm) and the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) were downloaded and read. GOV.UK permits reproduction of OGL content subject to the licence, with exceptions for identified non-Crown content. HSE permits reuse of Crown information and specifies its preferred attribution. The OGL permits copying, adapting and commercial/noncommercial reuse with attribution; it excludes third-party rights and does not imply endorsement. Each normalized document contains the source URL, publisher attribution and licence URL. The SFBB PDF also explicitly licenses its information under OGL, excluding logos and third-party photographs.

The permission recorded is for **text reuse**. Raw PDFs retain integral branding, photographs and diagrams for source verification; the manifest does not grant blanket republication rights to all those assets. The cloud ingestion companion is text, excluding images. No external images were downloaded to fill the HTML pages, and no third-party attachment rights were inferred from a linking page.

| Terms evidence | Direct acquisition state | Snapshot SHA-256 |
|---|---|---|
| [https://www.hse.gov.uk/help/copyright.htm](https://www.hse.gov.uk/help/copyright.htm) | HTTP 200; saved | `84f9305d0825e7e4635954f5c978dc12d388def73d25898401480d3e396212b0` |
| [https://www.gov.uk/help/terms-conditions](https://www.gov.uk/help/terms-conditions) | HTTP 200; saved | `53384b066f308dda81819404a791e8e83ec044419cdc52fc25bf6c571870153b` |
| [https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | HTTP 200; saved | `f5b2b9f2af63647cde889fa6c3508f5705925295b74912c68caa28dd37e64aa5` |
| [https://www.cfs.gov.hk/english/notices/notices.html](https://www.cfs.gov.hk/english/notices/notices.html) | HTTP 200; saved | `218ebe09c252ab186856eda0da6349d76e385b9f019530b23573c6cc317b295f` |
| [https://www.fehd.gov.hk/english/department/copyright.html](https://www.fehd.gov.hk/english/department/copyright.html) | HTTP 200; saved | `2a99beb937892f094c320381f61d7c6aa1ead32c239005b3e7f702f312609fe2` |
| [https://www.bunn.com/terms-of-use](https://www.bunn.com/terms-of-use) | HTTP 403; not saved | `null — no bytes acquired` |

[HTTP request ledger](../evaluation/knowledge-expanded/public/provenance/requests.jsonl) retains timestamps, requested/resolved URLs, HTTP status, content type, byte hashes, sizes, Last-Modified/ETag where supplied and errors. Successful bodies and licence pages are under `public/provenance/`. Terms and discovery pages are audit material, **not** documents in the quota.

### Excluded and unresolved candidates

[Excluded-source states](../evaluation/knowledge-expanded/public/provenance/excluded-source-states.jsonl) preserves 11 catalog/discovery records outside the acquired manifest. Their original paths, sizes and hashes are null.

- Catalog PUB-001/002/003/004/009: [CFS notice](https://www.cfs.gov.hk/english/notices/notices.html) and [FEHD notice](https://www.fehd.gov.hk/english/department/copyright.html) require prior written authorization for reproduction/adaptation/distribution. No operational source bodies were downloaded; no permission or account request was sent.
- Catalog PUB-005/006/008: GS1 full-source acquisition and applicable global-site reuse terms are unresolved in this batch. No claim of a global GS1 licence was inferred from national affiliates or implementation/patent policies. They remain uncounted.
- Catalog PUB-007: the prior catalog records HTTP 403. The blocked source was not retried or accessed via a mirror.
- Catalog PUB-010: discovery index only, never counted as a source document.
- BUNN commercial manuals: the [official terms](https://www.bunn.com/terms-of-use) were readable in web search before the shell attempt. They distinguish limited reference/marketing uses and restrict derivatives and aggregation without permission. Direct terms acquisition then returned **403**; no terms-page body/hash or manual was acquired, no bypass/retry followed, and no blanket cloud-corpus permission was asserted.
- The retired FSA copyright URL returned **410** in direct acquisition. That failed endpoint was not counted; current GOV.UK publication pages and current GOV.UK/OGL terms support the FSA materials acquired here.

## Fidelity and verification

[Verification results](../evaluation/knowledge-expanded/public/provenance/verification.json) record a passing offline acquisition audit:

- 24 unique families/document IDs/version IDs and 24 unique original-byte hashes; every original, normalized companion and terms snapshot matches its recorded size/hash.
- All 14 HTML documents use the entire single `gem-c-govspeak` publication body. Every substantive source text fragment of at least 15 characters was found in normalized text; heading counts, origin IDs and table counts were checked. Links were made absolute, ordered-list numbering retained and HTML table row/column spans preserved. Navigation, cookie banners and page furniture were excluded. All 20 externally linked images (19 HFSS diagrams and one food-label image) are explicitly marked not acquired; source captions and image URLs remain available.
- All 193 PDF pages are present in the raw originals. Embedded text is retained per page with `#page=N` source locators. The companion does not claim a visual facsimile, full diagram transcription, reconstructed table geometry or filled-in forms. Sparse-text pages are explicitly listed and marked in Markdown.
- Nine representative pages were rendered and visually reviewed: HSE CAIS12 p2; CAIS24 p6; recall guidance pp1/53/54; SFBB pp1/2/5/92. This is sampled visual review, not an exhaustive review of every page.
- Recall PDF pp53–54 contain **publisher example** recall/allergy posters as images. Embedded text omits the poster bodies. `image_text_missing_pages=[53,54]`; OCR was not run. The raw PDF contains them. Do not use the companion as evidence for poster fields it does not contain, or label those examples live incidents.
- Repository `pypdf` failed on a font descriptor in the SFBB pack. A bundled `pypdfium2` reader extracted all 100 pages without changing the PDF. The fallback and original hash are recorded in `fsa-sfbb-page-text.json` and manifest metadata. No dependency was installed or modified.
- HSE CAIS24's last-page footer prints CAIS23(rev3), although its first page, URL and official landing identify CAIS24. The anomaly is retained in metadata and source text. No silent correction to the original was made.
- Pairwise lowercase word 5-gram comparison covered 276 pairs. Maximum Jaccard similarity was **0.072523**, between kitchen ventilation and solid-fuel carbon-monoxide guidance; these are independently published documents with distinct operating conditions. Similarity is a screening signal, not semantic duplicate proof; family boundaries were also reviewed by title, publication and business purpose.

## Dates, applicability and stopping point

Acquisition timestamps are not publication or effective dates. Exact dates use the visible publication label where available. Several migrated FSA records expose 2026 `govuk:first-published-at` values while their visible publication labels are older; both are retained. HSE month/year footers and the recall guide's March 2019 cover are preserved as `publication_date_text`, with `publication_date=null` because the exact day is unknown. SFBB's exact PDF edition date is unresolved, so it is also null. No Last-Modified header is presented as an effective date. Supersession is not asserted.

This run used public HTTPS requests and official web search only. There were no accounts, paid API calls, model/embedding calls, source access-control workarounds or user screenshot requests. Work was confined to the assigned public directory, its source manifest and this report. Application import, frozen questions, synthetic corpus, aggregate schema, root dependencies, IH and deployment were not changed.

## Reproduction and handoff

`public/acquire.py` is the auditable public-download helper; its cached ledger prevents repeated requests to logged URLs, including 403 responses. `public/normalize.py` regenerates text companions and the acquired-only manifest offline. The SFBB fallback text file is bound to the original PDF SHA-256. `public/verify.py` checks the saved acquisition and writes verification evidence. These helpers live only inside the assigned public directory; they are not application code or installed dependencies.

To reproduce the offline checks from the repository root using the existing environment:

```powershell
$env:PYTHONIOENCODING='utf-8'
./.venv/Scripts/python.exe docs/evaluation/knowledge-expanded/public/normalize.py
./.venv/Scripts/python.exe docs/evaluation/knowledge-expanded/public/verify.py
```

Manifest SHA-256 at handoff: `47249ca2e2808dff18094ea71a3cdaf55f680527ab404ede2b7a7ee1f3a6f4ce`.
