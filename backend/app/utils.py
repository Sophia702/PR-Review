from datetime import datetime, timezone


def ensure_utc(dt: datetime) -> datetime:
    # SQLite round-trips DateTime columns as naive even with timezone=True,
    # so a value reloaded from the DB can come back without tzinfo. Assume
    # UTC rather than let arithmetic against a tz-aware datetime raise.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
