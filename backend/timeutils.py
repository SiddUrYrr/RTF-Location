from datetime import datetime, timezone


def utcnow() -> datetime:
    """
    Naive UTC timestamp.

    The database columns are timezone-less (`DateTime`), so we deliberately
    drop tzinfo after building an aware UTC value. This avoids the deprecated
    `datetime.utcnow()` while keeping naive/naive comparisons consistent.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
