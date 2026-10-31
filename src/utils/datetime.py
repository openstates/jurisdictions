from datetime import UTC, datetime


# Helper to make UTC datetimes
def ymd(y: int, m: int, d: int) -> datetime:
    return datetime(year=y, month=m, day=d, tzinfo=UTC)
