# MAIN PIPELINE (main.py) = orchestrator 
    - Takes a state as an argument (run by state)
    - calls parent pipeline (ocdid_pipline.py)
        - parent pipeline calls child pipeline (generate_pipeline.py)

## OCDid Pipeline: 
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
        - Generate a UUID
        - Store OCDid and UUID in DuckDB lookup table for re-runs. 

    - NOTE: Because we are storing this in DuckDB this can be run once... and
      skipped in future runs. 
    - @Matt: It might be helpful to backup to a .csv file as well... once we
      have the master list of OCDids we are good to go for future runs.
    - In the future we're going to have to run this pipeline but hopefully we
      can add the cousub and other missing ocdIDs to the civic data repo.

    -Return:
        OCDidIngestResp() model
            - UUID # id of the stub Division object
            - OCDidParsed # OCDID from Open Civic Data master list
            - raw record from Open Civic Data master list

    - Calls Child Pipeline (GeneratorReq ->)
        - Processes each individual OCDid record
        - returns (GeneratorResp)

## Generate Divisions, Jurisdictions Pipeline
2. For each Open Civic Data request - run the GeneratorPipeline 
    - Request  = GeneratorReq 
    - Response = GeneratorResp 
    - Runs the generator which will perform the following tasks:
        1. Log to a file
        2. Load  Creyton's csv
        2. Setup quarantine to store records did not match
            - tab in Creyton's file with a run date.
        3. Given the parsed OCDid, find a "place" match in the research 
            - Match defined by state + place_name (.to_lower())
            - Fuzzy string matching. 
            - If more than one match, fail 
            - If no match fail 
        4. If match... 
                - Generate a DivisonObj 
                    - ai call to generate arcGIS request
                - Generate a JurisdictionObj 
                    - ai call to return website for jurisdiction (wikipedia?)
                - include gnis identifier (geoid)
                - Store the .yaml files in the Division, Jurisdiction
                    - /<state>/<local>/<identifier.yaml>
                - Commit file to github? faster?
                - Update Creyton's spreadsheet with the OCDid, github path (with
                UUID) for the record
                    - Indicates we found a 
                    - update OCDID add UUID 
           If fail to match... 
            - Store in quarantine tab of Creyton spreadsheet with error message / reason code

        7. Return status in GeneratorResp

## Generate Stats 
3. Resolve Match Pipeline 
- Request object: 
    - Once all of the child workflows have completed 
    - Determine which records are in Creyton's sheet that were not in an OCDid
    - Add them to the quarantine ("missing OCDid, not found in Open Civic Data")
    - Run stats: 
        - Total files 

