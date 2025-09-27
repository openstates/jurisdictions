1. Fetch data from Open Civic Data repo
    Pipeline will run by state:
    - Pull Master list of OCDids form Open Civic Data (us.csv)
    - Pull OCDids from Open Civic Data (use the state directory "local" .csv)
    - For each record in the local list, pull the full data from master list.
        - We will work from the master list.
        - Convert this into a Division record.
            Sourcing:  "Initial ingest of master OCDids maintained by the Open Civic Data project."
        - Generate a UUID (timestamp)
        - Map fields in master list to Division model
        - convert the  model to .yaml and store the .yaml file with the UUID
          only as the name
        - Parse the OCDid in the OCDidParsed model

    -Return:
        OCDidIngestReq() model
            - UUID
            - filepath
            - OCDidParsed
            - raw record from the master list

2. Fetch the data from the master research spreadsheet (hereafter: Creyton's spreadsheet) by state (do a state code lookup)
    Pipeline will run by state:
    Request = OCDidIngestReq()
    - Load  Creyton's csv
    - Setup quarantine to store records did not match
    - Given the parsed OCDid, find a "place" match in the research
    - If match:
        - load the stub Division
        - Populate the data in Divison model
        - resave the now populated stub
        - update Creyton's spreadsheet with the OCDid for the record
            - Indicates we found a match
    - If not match:
        - add to quarantine, append to file.
