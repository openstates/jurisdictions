import requests
import csv

def fetch_csv_rows(url: str) -> list[dict]:
    response = requests.get(url)
    response.raise_for_status()
    decoded = response.content.decode('utf-8')
    reader = csv.DictReader(decoded.splitlines())
    return list(reader)