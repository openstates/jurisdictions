import json
import os

def load_state_code_lookup():
    """
    Loads the json stored here: data/state_lookup.json
    Returns:
        dict: State code lookup dictionary.
    """

    utils_dir = os.path.dirname(__file__)
    path = os.path.join(os.path.dirname(utils_dir), "state_lookup.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)