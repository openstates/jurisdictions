
DIVISIONS
Structural issues: 

- id: PASS
- ocdid: PASS
- country: PASS
- display_name: PASS
- geometries: FAIL 
    - Sourcing should not be included in each "Geometry" object. Sourcing should
      only be included in the top level "sourcing" field in the Divisions model.
      Within "sourcing" the source data should be structured as a nested
      dictionary object that mirrors the structure of the rest of the model
      (dotted field path). The data 
    - If the source for all fields is the same, the top-level "source" field can
    include only one source object per top level field on the SourceObj. 
    - Identifiers are also listed as nested objects and instead should be in the
  top-level model field "government_identifiers" as a list of associated
  government identifiers. 
    - Within the geometries.identifiers is a SourceObj, that should not be
    there. Sourcing should only be included in the top level "sourcing" field in
    the Divisions model. 
    - centroid null - can we fill?  
    - extent null - can we fill? 
government_identifiers 
 - add country code (ISO) to the list of identifiers (first identifier)

Data Issues: 
- file: tests/sample_output/updated_output_for_review/divisions/test/ca/local/marin_city_90ae7478-23af-54cb-b444-aa8e5e1d8db5.yaml

    - authority: census
        id_type: placefp
        value: '46420' WRONG 
    - The correct value is 

    - jurisdiction_id: 
    - Current:
    ocd-jurisdiction/country:us/state:ca/county:marin/cdp:marin_city/special_district:marin_city_community_services_district/governing_board
    - Expected: 
    Correct in Jurisdiction .yaml: 
    ocdid:
    ocd-jurisdiction/country:us/state:ca/county:marin/cdp:marin_city/special_district:marin_city_community_services_district/special_purpose_district
    - The jurisdiction_id should match the ocd_id in the corresponding jurisdiction
      .yaml file. 
   
Sourcing issues: 

JURISDICTIONS

Structural issues: 

- filename incorrect: CREYTON CHECKING IF GOVERNING BOARD IS CORRECT LEGAL NAME??
    - current:
      tests/sample_output/updated_output_for_review/jurisdictions/test/ca/local/marin_city_community_services_district_governing_board_b862068b-5a1f-5610-bc35-1b97b53f2d9a.yaml
    - expected: 
      tests/sample_output/updated_output_for_review/jurisdictions/test/ca/local/marin_city_community_services_district_b862068b-5a1f-5610-bc35-1b97b53f2d9a.yaml

Data issues: 

Structural issues: 
