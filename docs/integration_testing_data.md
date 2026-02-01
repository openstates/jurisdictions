# Prompt
Create sample data for the following places, each with their own division and
jurisdiction id.  The goal is to use this data to run integration tests. So, it should be real verifiable data. 
 
# Source .csvs
tests/sample_data/test_sample.csv
tests/sample_data/WA_TX_OH_sample.csv

# ocdids to generate data for
ocd-division/country:us/state:ca/place:sausalito
ocd-jurisdiction/country:us/state:ca/place:sausalito/legislature

ocd-division/country:us/state:ca/county:marin/cdp:marin_city 
ocd-jurisdiction/country:us/state:ca/county:marin/special_district:marin_city_community_services_district/governing_board

ocd-division/country:us/district:dc/anc:1a/council_district:1
ocd-jurisdiction/country:us/district:dc/anc:1a/government

ocd-division/country:us/state:wa/place:seattle/council_district:1
ocd-jurisdiction/country:us/state:wa/place:seattle/government

ocd-division/country:us/state:wa/place:tacoma
ocd-jurisdiction/country:us/state:wa/place:tacoma/government

ocd-division/country:us/state:tx/place:austin/council_district:8
ocd-jurisdiction/country:us/state:tx/place:austin/government


#sym:## Inputs and outputs 
## Input 
Source files contain a set of representative test records

tests/sample_data/testing_ocd_sample.csv
tests/sample_data/testing_creyton_sample.csv

## Output

### Output files
Each output should include the complete set of test records. 

1. a .yaml file stored in  jurisdictions/test/<state>/local for each Jurisdiction 
2. a .yaml file stored in  divisions/test/<state>/local for each Division 

### Output structure and data completeness
The structure and the data must be consisted across all output types. 
The output should include all defined values. If the true value is not available
in any of the source files: 
- first try searching the web using the known data as context
- If that also fails, use a placeholder value representing the missing data
  prefixed by "missing".  

### Output directory 
All files should be stored here. 
tests/sample_output

### Reference links: 
- [Census Fips
Codes](https://transition.fcc.gov/oet/info/maps/census/fips/fips.txt)
- [Tiger ArcGIS Rest API](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/)





