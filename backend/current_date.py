"""Tells models what today's date is. LLMs have no clock and otherwise answer
'what's the date?' with whatever date dominated their training data. The
message is rebuilt on every request and never stored, so old or compacted
conversations don't carry a stale date."""
import datetime
from contextvars import ContextVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# The browser's IANA timezone (e.g. "Asia/Dubai"), sent by the frontend in an
# X-Timezone header and captured by middleware in app.py.
request_timezone: ContextVar[str | None] = ContextVar("request_timezone", default=None)


def build_date_message() -> dict:
    now = None
    tz_name = request_timezone.get()
    if tz_name:
        try:
            now = datetime.datetime.now(ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, ValueError):
            now = None
    if now is None:
        now = datetime.datetime.now().astimezone()
        tz_name = now.tzname() or "local time"
    return {
        "role": "system",
        "content": (
            f"Today's date is {now.strftime('%A, %d %B %Y')} ({tz_name}). "
            "Use this whenever the user asks about the current date or day, or needs "
            "relative dates like 'tomorrow' or 'last week'."
        ),
    }
