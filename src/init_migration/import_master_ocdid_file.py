import pandas as pd


class ImportMasterOCDidFile:
    CIVIC_DATA_OCDIDS_URL = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv"
    CIVIC_DATA_LOCAL_OCDIDS = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us/state-{stusps}-local_gov.csv"

    def __init__(self):
        pass

    def load_master_ocdids(self) -> pd.DataFrame:
