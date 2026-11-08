DIVISIONS

Structural issues
- id: PASS
  - The six reviewed Division UUIDs match the reviewed branch's UUID5 derivation from ocdid. Preserve that branch-specific algorithm. An approved OCDID change requires coordinated dependent-ID/reference updates.
- ocdid: PASS — structural check only.
  - Marin City's registry coverage remains a separate REVIEW item under D04 below.
- country: PASS
  - Reviewed value: us. The requested ISO identifier below is an additional identifier, not a reason to silently change this field's case.
- display_name: PASS — field structure.
  - Entity type and identifier scope still require the record-specific checks below.
- geometries: REVIEW — requested structural changes; the observed nested sources/identifiers are allowed by the reviewed model.
  - Requested change: centralize geometry provenance in the Division's top-level sourcing. The current Geometry.source is intentional and model-valid; moving it requires an agreed model/generator change preserving geometry-version provenance.
  - Requested change: use nested source data mirroring model field paths. The current contract is a list of SourceObj entries with dotted strings in field, not a record-shaped dictionary. Kas must specify the intended encoding, including geometry/version selection, before implementation.
  - When one source supports all children of a top-level field, use one source object for that field instead of repeating it for every child. Retain separate sources where their scope, release, or dates differ.
  - Geometry identifiers should be represented in the Division's top-level government_identifiers list. Preserve the distinction between the division itself, parent geography, and a particular geometry/release when moving them.
  - Exact observed path: geometries[0].identifiers[0].source. The list entry is an Identifier containing its required SourceObj, not a SourceObj substituted for an Identifier. Removing that source requires changing the current Identifier contract as part of the requested redesign.
  - centroid: REVIEW — currently null where a boundary object is present. It can be derived after the correct geometry and reference period are accepted. Agree the centroid method and coordinate system; no centroid has been calculated in this review.
  - extent: REVIEW — currently null where a boundary object is present. Derive from the same accepted geometry and specify coordinate order/CRS; no extent has been calculated in this review.
- government_identifiers: REVIEW — requested ordering and consolidation; these are not current-model requirements.
  - Requested change: add the ISO country identifier first, using alpha-2 value US for these U.S. records. Its position in this list is the supplied review preference, not an ISO/current-schema ordering rule. Agree the authority/type vocabulary.
  - Consolidate associated identifiers here without duplicate or conflicting entries. Preserve leading-zero codes as strings.
  - Parent city, county, or ANC identifiers must remain explicitly scoped as parent/context identifiers; moving them to the top level must not turn them into district self identifiers. [D09–D11]
- sourcing: REVIEW — implementation contract.
  - Use the top-level property name sourcing consistently. Confirm the accepted nested-dictionary/field-path encoding and SourceObj serialization with Kas before changing generator/model output; this document does not invent a new YAML contract.

Data issues
- file: tests/sample_output/updated_output_for_review/divisions/test/ca/local/marin_city_90ae7478-23af-54cb-b444-aa8e5e1d8db5.yaml (reviewed YAML)
  - government_identifiers / Census PLACEFP: FAIL. [D01]
    - Current: authority: census, id_type: placefp, value: '46420'.
    - Expected: authority: census, id_type: placefp, value: '45820'.
    - GEOID 0645820, STATEFP 06, PLACEFP 45820, and LSAD 57 identify Marin City CDP. The earlier review reported that the captured upstream row was already correct; this pass did not re-read that spreadsheet. Trace the stale value to its actual origin. Census evidence
  - jurisdiction_id: FAIL — exact cross-reference mismatch. [D02]
    - Current: ocd-jurisdiction/country:us/state:ca/county:marin/cdp:marin_city/special_district:marin_city_community_services_district/governing_board.
    - Expected to match the existing Jurisdiction YAML: ocd-jurisdiction/country:us/state:ca/county:marin/cdp:marin_city/special_district:marin_city_community_services_district/special_purpose_district.
    - The Division's jurisdiction_id must exactly equal the corresponding Jurisdiction's ocdid. If a later approved canonical-identity decision changes that OCDID, update both records and all dependent references together. Corresponding Jurisdiction
  - ocdid registry coverage: REVIEW. [D04]
    - The exact Marin City CDP ID was absent from the pinned registry snapshot. Decide the accepted local/candidate exception or registry process; absence does not establish that the CDP does not exist or that the identifier syntax is invalid. Pinned registry
  - metadata.population.population: PASS for value; REVIEW for reference-period representation. [D06]
    - Retain 2993 as the 2020 decennial CDP population and attach that reference period. It is not an independently established current estimate or CSD population. Census population table
  - CDP/CSD relationship: REVIEW. [D23]
    - Marin City CDP and Marin City Community Services District are distinct entities. This review has not established coextensive legal boundaries.
- file: tests/sample_output/updated_output_for_review/divisions/test/ca/local/sausalito_c5c62304-e506-54bd-ab72-e4e14d62bba1.yaml (reviewed YAML)
  - Census identity: PASS for GEOID 0670364, STATEFP 06, PLACEFP 70364, and LSAD 25. Census evidence
  - Recorded county/legislative set: REVIEW — the earlier report stated that its preserved 2025 check corroborated Marin 041, Senate 002, Assembly 012. This pass did not repeat that overlay; this is not a new spatial PASS.
  - geometries: REVIEW boundary release and date provenance under Sourcing issues below. [D07/D24]
- file: tests/sample_output/updated_output_for_review/divisions/test/dc/local/anc_1a_district_1_c738edad-1ed5-57f7-80a3-a9ca4488cbfb.yaml (reviewed YAML)
  - geometries feature selection: FAIL. [D08]
    - Current: DCGIS layer 54, filter ANC_ID='1A', returning the whole commission.
    - Expected: DCGIS layer 55, filter SMD_ID='1A01', returning the single-member district. Retain the documented 2023 boundary reference. Exact SMD query
  - government_identifiers: FAIL for district self identity. [D09]
    - Current Census NAMELSAD ANC 1A and GEOID 11001 do not identify SMD 1A01.
    - Expected self identity: DCGIS SMD_ID='1A01'. Parent commission: ANC_ID='1A'.
    - Census GEOID 11001 identifies the DC county-equivalent. STATEFP 11 and COUNTYFP 001 remain valid location context; retain them with that scope. County-equivalent query
- file: tests/sample_output/updated_output_for_review/divisions/test/tx/local/austin_council_district_8_34071538-4f6c-58fe-9a31-5900590cecf0.yaml (reviewed YAML)
  - government_identifiers: FAIL — wrong geographic entity. [D10]
    - Current GEOID 4845390165 and LSAD 22 identify Austin CCD, not Austin city or Council District 8. The CCD's COUSUBFP is 90165. Census evidence
    - Expected district self identity: municipal COUNCIL_DISTRICT='8'.
    - Parent city only: GEOID 4805000, PLACEFP 05000, LSAD 25. Do not substitute the city GEOID as district self identity. City query
  - County/legislative associations: REVIEW — provisional spatial candidates. [D12]
    - The earlier current-municipal-polygon × ACS2025 diagnostic returned Hays 209 and Travis 453; Senate 014,025; House 045,047,048,049. Williamson 491 was absent from that diagnostic.
    - These are not accepted historical replacement values. Approve compatible reference periods and reproduce the overlay before applying them. Municipal layer
  - geometries: []: REVIEW — missing coverage. [D14]
    - Candidate: municipal District 8 query. Add geometry if required for acceptance; otherwise record the incomplete boundary coverage explicitly.
- file: tests/sample_output/updated_output_for_review/divisions/test/wa/local/seattle_council_district_1_3f69bd27-211e-5717-8087-752df1db0bde.yaml (reviewed YAML)
  - government_identifiers: FAIL when parent-city fields are presented as district self identity. [D11]
    - Current GEOID 5363000, NAMELSAD Seattle city, and LSAD 25 identify the parent city.
    - Expected district self identity: municipal C_DISTRICT='1'. Retain city identifiers only with parent scope. Municipal layer
  - Legislative associations: REVIEW — provisional spatial candidates. [D13]
    - The recorded list reproduces the captured citywide list. The including-water district polygon × ACS2025 diagnostic returned 011,034,037,043 in both chambers.
    - District 043 intersected by approximately 3 m² in the earlier diagnostic. That is not an accepted representation relationship or a certified geodesic area; a separate remote geodesic calculation failed. Adjudicate source alignment/slivers without inventing a threshold.
  - geometries: []: REVIEW — missing coverage. [D14]
    - Candidate: District 1 including-water query. Use full territory rather than a shoreline-clipped display product when full governing territory is intended; approve the reference period.
- file: tests/sample_output/updated_output_for_review/divisions/test/wa/local/tacoma_c104c614-3662-5202-ac00-c348b7c31e4f.yaml (reviewed YAML)
  - Census identity: PASS for GEOID 5370000, STATEFP 53, PLACEFP 70000, and LSAD 25. Census evidence
  - Recorded county/legislative set: REVIEW — the earlier report stated that its preserved 2025 check corroborated Pierce 053 and 027,028,029 in both chambers. This pass did not repeat that overlay.
  - geometries: []: REVIEW — missing coverage. [D14]
    - Candidate: 2025 Tacoma query. Populate if required for acceptance; otherwise identify the missing boundary coverage.

Sourcing issues
- Division sourcing placement: REVIEW — requested redesign, not a current-model violation.
  - Requested direction: centralize geometry and identifier provenance in top-level sourcing. Both are explicitly represented by the reviewed model. Agree the revised contract before moving them; preserve source, feature, value and geometry-version scope.
- Marin City and Sausalito: geometry product/release: FAIL for reproducibility of the claimed release. [D07]
  - Current geometry metadata claims 2025 while the generic service inspected in the prior review advertised January 1, 2026 geography.
  - Expected: a release-specific 2025 product or preserved 2025 snapshot. Candidate queries: Marin City and Sausalito. This does not prove that every polygon changed.
  - Identify TIGERweb separately from a TIGER/Line ZIP; they are different artifacts even when they refer to the same year.
- Geometry dates: REVIEW. [D24]
  - A dataset reference date is not independently established legal boundary effectiveness. Retain January 1, 2025 only as an explicitly accepted/documented approximation under the agreed valid_from contract.
  - Preserve the documented 2023 DC boundary reference. Approve Austin/Seattle reference alignment before accepting historical overlays.
- Retrieval and verification dates: REVIEW — provenance gaps. [D19]
  - Record source product/release, source URL, reference/publication period, actual retrieval time, and field verification separately. Do not backfill guessed dates or treat the November 2026 review as proof that every field was accurate in 2025.
  - Preserve inherited human_researched labels as inherited claims; distinguish subsequent programmatic/AI-assisted review.
- Exact geometry retrieval: REVIEW — previously reported result, not a new geometry check.
  - The prior review reported one nonempty Polygon/MultiPolygon from each of the six candidate GeoJSON queries. This pass reconfirmed key feature identities using attribute queries, but did not revalidate all six geometry payloads. Austin/Seattle historical-vintage acceptance, centroid/extent derivation, and final overlay acceptance remain REVIEW.

JURISDICTIONS

Structural issues
- id: PASS
  - The six reviewed Jurisdiction UUIDs match the reviewed branch's UUID5 derivation from ocdid. A display-name/filename-only correction does not justify changing the UUID under that implementation.
- Marin City filename/name: REVIEW — agency versus governing-body representation. [D03]
  - Current: tests/sample_output/updated_output_for_review/jurisdictions/test/ca/local/marin_city_community_services_district_governing_board_b862068b-5a1f-5610-bc35-1b97b53f2d9a.yaml.
  - Expected if the record represents the district agency: tests/sample_output/updated_output_for_review/jurisdictions/test/ca/local/marin_city_community_services_district_b862068b-5a1f-5610-bc35-1b97b53f2d9a.yaml.
  - The agency is Marin City Community Services District; its website calls the body the Board of Directors. County election material also uses Governing Board Member. “Governing Board” is therefore not inherently incorrect wording, but these sources do not establish the existing filename phrase as the agency's legal name. Decide whether the record represents the agency or its body before renaming. LAFCo; official board page; county terminology
  - If agency representation is confirmed, update name and regenerate the filename consistently. Preserve the UUID while the OCDID is unchanged; resolve any separate canonical OCDID change with its dependent references.
- division_relationships and term.number_of_positions: REVIEW — subject scope. [D23]
  - A citywide government and an individual council district are different scopes. Record full governing territory and district-to-parent relationships without implying exclusive authority or CDP/CSD boundary equality.
  - Clarify that the supported counts below describe the specified council/board/commission rather than every elected office in the jurisdiction.
- term.last_known_term_end_date: REVIEW — field meaning. [D05]
  - The reviewed field name says end date while its model description says start date. Agree start/end meaning, seat/cohort scope, and regular versus partial terms before assigning a replacement date. Reviewed model
- organizations, governing_charter, census_government_id, and other null/empty fields: REVIEW — coverage contract. [D20]
  - Optional nulls do not independently fail the sample or prove that no body, charter, term limit, government-unit ID, or relationship exists.
  - Agree required coverage. A Census geography GEOID must not be substituted for a Census government-unit ID.
  - Do not duplicate a board/commission beneath itself when choosing organization scope. A general enabling law is not automatically a separately verified local charter.

Data issues
- file: tests/sample_output/updated_output_for_review/jurisdictions/test/ca/local/marin_city_community_services_district_governing_board_b862068b-5a1f-5610-bc35-1b97b53f2d9a.yaml (reviewed YAML)
  - name: REVIEW — use Marin City Community Services District if this is the agency record; its body is the Board of Directors. See filename decision above. [D03]
  - Matching Division reference: FAIL in the pair, specifically the Division's jurisdiction_id. This does not independently establish that the Jurisdiction's own ocdid is wrong. Use the existing Jurisdiction ocdid as the Division target shown above; any later approved canonical change must remain coordinated. [D02]
  - term.duration: PASS — four regular years. term.number_of_positions: PASS for the five-member board; jurisdiction-wide field scope remains REVIEW. LAFCo
  - term.last_known_term_end_date: FAIL — unsupported precision. [D05]
    - Current: 2026-12-31T00:00:00Z.
    - Expected: no unsupported exact date; remove/mark unknown under the accepted contract until evidence identifies a seat/cohort and the applicable start/end rule. The county notice distinguished full and short terms, not one universal board end date. County notice
  - term.term_limits: REVIEW — recorded unknown; this is not evidence of no limits.
- file: tests/sample_output/updated_output_for_review/jurisdictions/test/ca/local/sausalito_city_government_7539e65b-3a49-5e24-82b4-3a5bc6f72aad.yaml (reviewed YAML)
  - term.duration: PASS — four regular years. term.number_of_positions: PASS for the five-member council. City government
  - Mayor/vice-mayor selection: PASS as a separate annual officer selection; it does not reduce council membership to a one-year term. Official council page
  - Four URL references: FAIL for intended content. [D17]
    - Government/term source: current → expected.
    - Council metadata source: current → expected.
    - People: current → expected.
    - Meetings: current → expected.
    - Update every repeated source citation as well as discovery URLs. On November 1 the legacy paths were recorded as 404; on November 3 direct requests returned identical generic news/events content with HTTP 200. The November 8 direct recheck again returned the same generic news/events page for all four legacy paths, with the same byte hash. The failure is wrong-purpose content, not a claim that every request always returns 404.
  - governing_charter: REVIEW — documented general-law city form does not establish a separate local charter; broader enabling-authority selection remains a coverage decision.
- file: tests/sample_output/updated_output_for_review/jurisdictions/test/dc/local/anc_1a_government_a598df3f-3f39-55a6-bb32-fe9e77b835e2.yaml (reviewed YAML)
  - term.duration: PASS — two regular years. term.number_of_positions: PASS for ten SMD seats; the previous DCGIS query returned 1A01 through 1A10. Official OANC; SMD roster query
  - Term start: PASS for the cited statutory rule — noon January 2 after election, or noon on the day after certification, whichever is later. This is not a universal term-end date. D.C. Code
  - metadata.urls / people: REVIEW — official-source preference. [D18]
    - Current: OpenANC legacy URL, which successfully redirects to OpenANC.
    - Preferred official source: OANC ANC 1A profile. The secondary link is not a demonstrated broken link.
  - Mailing address and commission website: PASS within the prior official-profile check — 3400 11th Street NW, Suite #200, Washington, DC 20010; https://anc1a.org/.
- file: tests/sample_output/updated_output_for_review/jurisdictions/test/tx/local/city_of_austin_69a2420e-4e10-5d98-8a7b-07c9b40811b1.yaml (reviewed YAML)
  - term.duration: PASS — four regular years. term.number_of_positions: PASS for eleven council positions including mayor. Published charter
  - term.term_limits: FAIL — incomplete rule summary. [D15]
    - Current: 2 consecutive terms.
    - Expected: preserve Article II §5's separate mayor/non-mayor council service treatment, the more-than-two-year partial-term rule, and the petition exception requiring at least 5% of qualified voters of the electing territory. Do not present the limit as unconditional. Published rule
  - metadata.urls: REVIEW — working redirects/canonical destinations. [D25]
    - People: current → canonical council page.
    - Meetings: current → canonical meetings page.
  - Municode term-source access: REVIEW — the prior direct request returned 403. Use the retrieved official published charter evidence for supported rule details; do not call the restricted endpoint a dead/404 link. [D25]
- file: tests/sample_output/updated_output_for_review/jurisdictions/test/wa/local/seattle_city_government_dd83c671-f854-59c5-bee3-21223377228f.yaml (reviewed YAML)
  - term.duration: PASS — four regular years. term.number_of_positions: PASS for nine council seats, seven district and two at-large; separately elected executive/other offices are outside this count. Official City Clerk district explanation confirms the regular structure. This does not certify individual incumbents or partial terms.
  - Term/people/meetings URLs: REVIEW — access and destination verification. [D25]
    - Current term source: https://www.seattle.gov/cityclerk/agendas-and-legislative-resources/terms-of-office-for-elected-officials.
    - Readable source candidate in the prior review: hyphenated City Clerk terms page.
    - Current people: https://www.seattle.gov/council/meet-the-council.
    - Current meetings: https://www.seattle.gov/cityclerk/agendas-and-legislative-resources/city-council-agendas.
    - Direct 403 responses establish an access restriction, not 404/dead content. Exact legacy-path and people/meetings destination content still needs confirmation.
  - term.term_limits: REVIEW — null does not establish that no limit exists.
- file: tests/sample_output/updated_output_for_review/jurisdictions/test/wa/local/tacoma_city_government_104f8f72-25fb-56ae-9a22-b4f1e0ac8ccf.yaml (reviewed YAML)
  - term.duration: PASS — four regular years. term.number_of_positions: PASS for nine positions including mayor. Published charter
  - term.term_limits: REVIEW — supported rule omitted; populate if term-limit coverage is required. [D16]
    - Current: null.
    - Expected when required: Charter §2.3.5's maximum of ten consecutive years serving on council as councilmember, mayor, or a combination.
    - Do not substitute the rejected 2024 proposed change for adopted law. The city's own review summary identifies term-limits Amendment No. 6 as failed. Charter; official 2024 charter-review summary

Sourcing issues
- Top-level provenance: REVIEW — align with the agreed sourcing contract.
  - Keep source attribution associated with its exact supported field. The supplied detailed source-placement changes concern Divisions; confirm any corresponding Jurisdiction schema changes rather than silently assuming them.
- All Jurisdiction files: historical accuracy/retrieval evidence: REVIEW. [D19]
  - Legacy accurate_asof/`last_updated` timestamps do not independently prove field accuracy at those times. Null retrieval dates remain gaps; do not backdate new verification or advance last_updated just because this document was edited.
- Sausalito: source citations: FAIL for intended content. [D17]
  - Apply all four replacements above, including repeated sourcing and term/metadata citations. Check final content, not only HTTP success.
- ANC 1A: source authority: REVIEW. [D18]
  - Prefer the official OANC profile when commissioner information is required; record OpenANC as secondary if retained. Working secondary evidence is a source-preference decision, not automatically false data.
- Austin/Seattle: redirects and restricted sources: REVIEW. [D25]
  - Preserve the distinction among successful redirects, wrong-purpose pages, unavailable evidence, and 403 access restrictions. An official source need not use a .gov domain; authority follows the publishing agency and evidence.
- organizations and governing_charter: REVIEW. [D20]
  - Model support alone does not establish a local factual value. Use field-specific local/official evidence if populating; a model's vocabulary/default source does not prove that a particular body exists.

SHARED VALIDATION ISSUES

Data issues
- file: tests/fixtures/sources/civicdata_divisions.csv (reviewed fixture)
  - Austin parent-city control: FAIL. [D21]
    - Current: GEOID 4845390165, label Austin city, PLACEFP 01000.
    - Expected parent city: GEOID 4805000, PLACEFP 05000. Keep Council District 8's municipal self identity separate.
    - Correct the fixture and dependent integration assertions together through the applicable maintainer process; a passing test with wrong expected facts does not validate those facts.
- Pipeline factual validation: REVIEW — required verification remains incomplete. [D22]
  - Existing round-trip/fixture tests can preserve incorrect input. Retain mechanics checks and add independently sourced expected facts, wrong-entity controls, and source → match → normalize → render → reload readback.
  - Earlier review-reported November 1 results at the pinned revision (not independently rerun or matched to raw test reports in this pass): golden suite 22 passed / 4 failed / 12 expected failures; generate-pipeline integration 16 passed / 1 warning. These are historical results, not new executions or production certification.
  - The four golden failures concerned three date expectations and an older fixture/UUID expectation; the separate direct check found all twelve reviewed UUIDs matched the current derivation. Do not label the reviewed IDs incorrect on that basis.
Completion requirements
- Reconcile the pinned observations against the current branch before applying changes. Reuse existing authorization, preserve other work, and read applicable repository instructions for protected model/fixture/golden edits.
- Resolve only decisions needed for a particular change; continue other authorized independent corrections.
- Confirm required versus optional coverage, parent/self/body scope, term-date meaning, geometry reference periods, and sourcing serialization. [D05/D09–D14/D19/D20/D23/D24]
- Fix incorrect facts at their source/mapping/generator origin, not only in rendered YAML. Regenerate and read back the twelve retained samples under the agreed structure.
- Check exact cross-references, ISO identifier order, string-preserved codes, absence of nested geometry SourceObj entries, and retained source-to-field attribution.
- Keep all D01–D25 dispositions visible. Report implemented changes separately from verified changes; list decisions, source gaps, permitted unknowns, exact commands/results, and the tested commit.
- Do not mark factual acceptance complete while required findings remain unresolved. No push, merge, publication, source-system write, or message is part of this document revision.

EVIDENCE RECORD
The table below retains the earlier capture hashes. The November 8 recheck independently downloaded the California/Washington 2025 PLACE ZIPs, Texas 2025 COUSUB ZIP, and pinned OCD registry and reproduced those four hashes exactly. Other historical hashes remain inherited and were not independently reverified in this pass. Current rolling Census metadata produced a different hash and still described January 1, 2026 geography; it must not be treated as the old captured bytes. Pinned GitHub links identify the reviewed revision; live official/GIS endpoints can change.
Artifact	Original-file SHA-256
ca_place_2025	2b59dc5d54c69c7a451795401fc2a1c1c68b172f1d912d3486080e04a83e23e8
wa_place_2025	b99039759e33cf931175302da80de9bd8d284c384721d52efde34dfbef2b64f5
tx_cousub_2025	460b6d18795be5f0a21955c8c7071a7b0474c57be9c51ba4b386110e32f12f8a
tacoma_charter	4e59a02dab19388f9ec60d14860a83fb5229b474eaf46da9a06e2f2749815cdf
austin_term_limits	c31d163c7cb8f16b8ff7f18ac06ba07f54654972c72f9716ec14319edc3ff4a3
marin_2025_geom	fda2963eeba3485b872107d9550a48f721b19103f9de2bec6b523bbf08362075
sausalito_2025_geom	98360190f3167d511a89acb05db2c710577ba76e580ff45a267988eb276f4842
tacoma_2025_geom	18df843920f38a9ff37fbccbe1c7804ec2518bc68ca6f7d6d23b43393e99cc27
dc_smd_1a01	f9b0dd4551952949f8ea3fe489855c55300808f632b4ef4953b1d1e35d9aa7e8
austin_d8_geometry	7d9bccde07d177ae3631a11c3f84c2988d7074e5016af7b6dbb14010b834c8e7
seattle_d1_water_geom	b840a5ddb732c4174e0e89f886af0c32cc0da22ca71e13e295621f74a2f165ed
rolling_places_metadata	8a75ef2c9e1a3b5ae69585b6b9a6d0ffd2047b40ff83363d020249779028be11
Connecticut 2025 COUSUB archive	2a30bc276de4d69ae94d92c87881ff85905f5a16680af485c0e15a253c5d6ed1
Pinned OCD registry	f1297a1d2dbe1f1b691a9ebeb0cff3808228a466d95b3d13336a4e55a9f53388


<!-- Source references retained from the reviewed document. -->
