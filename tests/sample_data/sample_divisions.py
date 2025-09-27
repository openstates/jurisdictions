"""
Script to import divisions data from a Google Sheet and convert each row into a Division object.
"""
import csv
import requests
from typing import List
from models.division import Division, Geometry
from models.source import SourceObj, SourceType
from models.jurisdiction import Jurisdiction, TermDetail, SessionDetail, ClassificationEnum
from datetime import datetime
from enum import Enum
import json
import os
from src.utils.str_utils import zero_pad_value
import pandas as pd
from init_migration.import_divisions import load_state_code_lookup, fetch_csv_rows

# TODO: Update this to the correct CSV export URL for your Google Sheet
DIVISIONS_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/export?format=csv&gid=1481694121"

JURISDICTIONS_SHEET_CSV_URL = ""

stusps = {} # placeholder

# split on "/place"
# split on "/county"
CIVIC_DATA_OCDIDS = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/refs/heads/master/identifiers/country-us.csv"

CIVIC_DATA_LOCAL_OCDIDS = f"https://github.com/opencivicdata/ocd-division-ids/tree/master/identifiers/country-us/state-{stusps}-local_gov.csv"


def main():
    rows = fetch_csv_rows(DIVISIONS_SHEET_CSV_URL)
    df = pd.DataFrame(rows)

    # Ensure state and LSAD columns exist
    if 'STATEFP' not in df.columns or 'LSAD' not in df.columns:
        raise ValueError('CSV must contain STATEFP and LSAD columns')

    # Define target states
    target_states = ["53", "48", "39"]  # Washington, Texas, Ohio


    # b) 150 samples stratified by LSAD and state
    # Group by (STATEFP, LSAD), sample proportionally
    stratified_sample = (
        df.groupby(['STATEFP', 'LSAD'], group_keys=False)
        .apply(lambda x: x.sample(n=min(max(1, int(150/df.groupby(['STATEFP', 'LSAD']).ngroups)), len(x)), random_state=42))
    )
    # If more than 150, sample down
    if len(stratified_sample) > 150:
        sample_a = stratified_sample.sample(n=150, random_state=42)
    else:
        sample_a = stratified_sample

    # Remove already sampled records from the pool
    remaining = df.drop(index=sample_a.index)

    # From remaining, take a stratified sample (by STATEFP and LSAD) of 150 from the three states
    remaining_target_states = remaining[remaining['STATEFP'].isin(target_states)]
    if not remaining_target_states.empty:
        n_groups = remaining_target_states.groupby(['STATEFP', 'LSAD']).ngroups
        stratified_c = (
            remaining_target_states.groupby(['STATEFP', 'LSAD'], group_keys=False)
            .apply(lambda x: x.sample(n=min(max(1, int(150/n_groups)), len(x)), random_state=42))
        )
        if len(stratified_c) > 150:
            sample_b = stratified_c.sample(n=150, random_state=42)
        else:
            sample_b = stratified_c
    else:
        sample_b = pd.DataFrame()

    print(f"Sample A (150 stratified by LSAD/state): {len(sample_a)} records")
    print(f"Sample B (150 from remaining WA, TX, OH): {len(sample_b)} records")

    # Optionally, export samples to CSV for inspection
    sample_a.to_csv('random_sample_by_LSAD_STATEFP.csv', index=False)
    sample_b.to_csv('WA_TX_OH_sample.csv', index=False)


if __name__ == "__main__":
    main()
