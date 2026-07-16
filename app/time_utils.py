import datetime


def local_now() -> datetime.datetime:
    # Store local machine wall-clock time as naive datetime for consistency
    # with existing SQLite DateTime columns.
    return datetime.datetime.now()


def local_tzinfo() -> datetime.tzinfo:
    tz = datetime.datetime.now().astimezone().tzinfo
    if tz is None:
        return datetime.timezone.utc
    return tz
