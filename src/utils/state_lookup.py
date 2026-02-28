import json
from pathlib import Path

def load_state_code_lookup():
    """
    Loads state lookup data from src/data/state_lookup.json.
    Returns:
        list[dict]: State code lookup records.
    """
    data_dir = Path(__file__).resolve().parents[1] / "data"
    path = data_dir / "state_lookup.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
