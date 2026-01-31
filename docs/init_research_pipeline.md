MAIN PIPELINE (main.py) = orchestrator


- Calls ocd_pipeline.py (handles fetching the OCDids and storing them in db)
    - 

1. Fetch data from Open Civic Data repo (ocd_pipeline.py)
    Pipeline will run by state:
    - Pull Master list of OCDids form Open Civic Data (us.csv) (divisons)
    - Pull OCDids from Open Civic Data (use the state directory "local" .csv)
    - For each record in the local list, pull the full data from master list.
        - We will work from the master list.
        - Convert this into a stub for a Division record.
            Sourcing:  "Initial ingest of master OCDids maintained by the Open Civic Data project."
        - Generate a UUID (timestamp)
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

CHILD PIPELINE
2. For each Open Civic Data request - run the GeneratorPipline 
    - Request  = GeneratorReq 
    - Response = GeneratorResp 
    - Runs the generator which will 
        1. Log to a file
        2. Load  Creyton's csv
        2. Setup quarantine to store records did not match
        3. Given the parsed OCDid, find a "place" match in the research 
        4. If match... 
                - Generate a DivisonObj 
                - creates an identifier with a hashed version
                - Generate a JurisdictionObj 
                - Populate the data in Division model
                    - ai call to find the argis server and return the url.
                - Save the populated Division object
        - update Creyton's spreadsheet with the OCDid for the record
            - Indicates we found a match
        - build a Jurisdictions record 
            - ai call to return website for jurisdiction (wikipedia?)
                - includes gnis identifier (geoid)
            - Store the .yaml files in the correct directory 
                - /<state>/<local>/<identifier.yaml>
            - Store it in a tab of the google doc if successful (or on Creyton's
              sheet.)
           If no match 
            - Store in quarantine file with error message / reason code
            - Will store it in a tab of the google doc (append only)

    - If not match:
        - add to quarantine, append to file.

        7. Return status in GeneratorResp

2. Fetch the data from the master research spreadsheet (hereafter: Creyton's spreadsheet) by state (do a state code lookup)
    Pipeline will run by state:
    Request = OCDidIngestReq()


