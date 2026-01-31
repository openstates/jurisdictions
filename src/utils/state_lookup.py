import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # this is jurisdictions/src
DATA_PATH = ROOT / "state_lookup.json"

def load_state_code_lookup():
    """
    Loads the json stored here: data/state_lookup.json
    Returns:
        dict: State code lookup dictionary.
    """

    with DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)