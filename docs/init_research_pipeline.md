# MAIN PIPELINE (main.py) = orchestrator 
    - Takes a state as an argument (run by state)
    - calls parent pipeline (ocdid_pipline.py)
        - parent pipeline calls child pipeline (generate_pipeline.py)

## Parent Pipeline: 
1. Fetch data from Open Civic Data repo (ocd_pipeline.py)
    Pipeline will run by state:
    - Pull Master list of OCDids form Open Civic Data (us.csv) (divisons)
    - Pull OCDids from Open Civic Data (use the state directory "local" .csv)
    - For each record in the local list, pull the full data from master list.
        - We will work from the master list.
        - Convert this into a stub for a Division record.
            Sourcing:  "Initial ingest of master OCDids maintained by the Open Civic Data project."
        - Generate a UUID (timestamp) 
            - as of 1/31 agreed we are going to store uuid/ocd-id in DuckDB
              lookup table
        - Map fields in master list to Division model
        - convert the  model to .yaml and store the .yaml file with the UUID
          only as the name
        - Parse the OCDid in the OCDidParsed model
        - Generate a UUID, store it in DuckDB lookup table

    -Return:
        OCDidIngestResp() model
            - UUID # id of the stub Division object
            - OCDidParsed # OCDID from Open Civic Data master list
            - raw record from Open Civic Data master list

    - Calls Child Pipeline (GeneratorReq ->)
        - Processes each individual OCDid record
        - returns (GeneratorResp)

## Child Pipeline
2. For each Open Civic Data request - run the GeneratorPipeline 
    - Request  = GeneratorReq 
    - Response = GeneratorResp 
    - Runs the generator which will 
        1. Log to a file
        2. Load  Creyton's csv
        2. Setup quarantine to store records did not match
        3. Given the parsed OCDid, find a "place" match in the research 
            - Match defined by state + place_name (.to_lower())
        4. If match... 
                - Generate a DivisonObj 
                    - ai call to generate arcGIS request
                - Generate a JurisdictionObj 
                    - ai call to return website for jurisdiction (wikipedia?)
                - includes gnis identifier (geoid)
                - Populate the data in Division model
                    - ai call to find the argis server and return the url.
                - Store the .yaml files in the Division, Jurisdiction
                    - /<state>/<local>/<identifier.yaml>
                - Update Creyton's spreadsheet with the OCDid for the record
                    - Indicates we found a match
           If no match 
            - Store in quarantine tab of Creyton spreadsheet with error message / reason code

        7. Return status in GeneratorResp



