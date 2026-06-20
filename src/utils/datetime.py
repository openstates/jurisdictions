from datetime import datetime, timezone


# Helper to make UTC datetimes
def ymd(y: int, m: int, d: int) -> datetime:
    return datetime(year=y, month=m, day=d, tzinfo=timezone.utc)
