"""Strict, offline weekly iCalendar import; no remote access or recurrence expansion."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .core.contracts import Event

SERVICE = "local-calendar"
ACCOUNT = "weekly-ics"
DEFAULT_ZONE = "Asia/Barnaul"  # Altai State University local civil time, UTC+7
MAX_ICAL_BYTES = 96 * 1024
MAX_EVENTS = 80
MAX_LINES = 1800


def clean_text(value, limit=1800):
    """Unescape iCalendar TEXT fields, preserving only inert display text."""
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError("invalid calendar text")
    if re.search(r"\\(?![nN,;\\])", value):
        raise ValueError("invalid iCalendar escape")
    value = re.sub(r"\\[nN]", "\n", value)
    value = value.replace(r"\,", ",").replace(r"\;", ";").replace(r"\\", "\\")
    return "".join(ch for ch in value if ch in "\n\t" or
                   (ord(ch) >= 32 and not 127 <= ord(ch) <= 159 and
                    ch not in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))[:limit]


def parse_time(value, params, zone):
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        raise ValueError("all-day entries are not lessons")
    if set(params) - {"TZID"}:
        raise ValueError("unsupported calendar date parameters")
    if not re.fullmatch(r"\d{8}T\d{6}Z?", value):
        raise ValueError("unsupported calendar date format")
    utc = value.endswith("Z")
    if utc and params:
        raise ValueError("conflicting calendar timezone")
    naive = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    if utc:
        result = naive.replace(tzinfo=timezone.utc)
    else:
        tzname = params.get("TZID", zone)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_+./-]{0,99}", tzname) or ".." in tzname:
            raise ValueError("invalid timezone")
        try:
            tz = ZoneInfo(tzname)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            raise ValueError("unsupported timezone") from None
        result = naive.replace(tzinfo=tz)
        if result.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != naive:
            raise ValueError("invalid local wall time")
    return result.astimezone(timezone.utc)


def week_of(moment, zone):
    local = moment.astimezone(ZoneInfo(zone)).date()
    return (local - timedelta(days=local.weekday())).isoformat()


def parse_ical(payload, zone=DEFAULT_ZONE, provenance='manual-ics'):
    if provenance not in ('manual-ics', 'subscription-ics'):
        raise ValueError("unsupported calendar provenance")
    if not isinstance(payload, str):
        raise ValueError("calendar upload must be UTF-8 text")
    if not 0 < len(payload.encode("utf-8")) <= MAX_ICAL_BYTES:
        raise ValueError("calendar file too large")
    if "\x00" in payload or "\ufffd" in payload or "\r" in payload.replace("\r\n", ""):
        raise ValueError("invalid calendar line endings")
    if payload.startswith("\ufeff"):
        payload = payload[1:]
    lines = []
    for row in payload.replace("\r\n", "\n").split("\n"):
        if len(row.encode("utf-8")) > 4096:
            raise ValueError("calendar line too long")
        if row.startswith((" ", "\t")):
            if not lines:
                raise ValueError("orphaned folded line")
            lines[-1] += row[1:]
        elif row:
            lines.append(row)
        if len(lines) > MAX_LINES:
            raise ValueError("calendar too complex")
    if not lines or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
        raise ValueError("not a complete iCalendar")
    stack, records, seen = [], [], set()
    entry = None
    version = None
    for row in lines:
        if ":" not in row:
            raise ValueError("invalid iCalendar property")
        left, value = row.split(":", 1)
        parts = left.split(";")
        name = parts[0]
        if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,63}", name):
            raise ValueError("invalid iCalendar property name")
        params = {}
        for part in parts[1:]:
            if "=" not in part:
                raise ValueError("invalid iCalendar parameter")
            key, val = part.split("=", 1)
            if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,39}", key) or key in params:
                raise ValueError("duplicate iCalendar parameter")
            params[key] = val.strip('"')
        if name == "BEGIN":
            if params or value not in ("VCALENDAR", "VEVENT", "VTIMEZONE", "STANDARD", "DAYLIGHT", "VALARM"):
                raise ValueError("unsupported iCalendar component")
            if (value == "VCALENDAR" and stack) or (value == "VEVENT" and stack != ["VCALENDAR"]):
                raise ValueError("invalid iCalendar nesting")
            if value in ("STANDARD", "DAYLIGHT") and (not stack or stack[-1] != "VTIMEZONE"):
                raise ValueError("invalid VTIMEZONE component")
            if value == "VTIMEZONE" and stack != ["VCALENDAR"]:
                raise ValueError("invalid VTIMEZONE location")
            if value == "VALARM" and stack != ["VCALENDAR", "VEVENT"]:
                raise ValueError("invalid VALARM location")
            stack.append(value)
            if value == "VEVENT":
                entry = {}
        elif name == "END":
            if params or not stack or stack[-1] != value:
                raise ValueError("unbalanced calendar structure")
            if value == "VEVENT":
                records.append(entry)
                if len(records) > MAX_EVENTS:
                    raise ValueError("too many calendar events")
                entry = None
            stack.pop()
        elif stack == ["VCALENDAR"]:
            if name == "VERSION":
                if version is not None:
                    raise ValueError("duplicate calendar version")
                version = value
        elif stack == ["VCALENDAR", "VEVENT"]:
            if name in ("RRULE", "RDATE", "EXDATE", "RECURRENCE-ID"):
                raise ValueError("recurring lessons require a separate import format")
            if name in ("UID", "DTSTART", "DTEND", "SUMMARY", "LOCATION", "DESCRIPTION", "STATUS"):
                if name in entry:
                    raise ValueError("duplicate calendar event field")
                entry[name] = (value, params)
        elif not stack and row != "END:VCALENDAR":
            raise ValueError("trailing calendar data")
    if stack or version != "2.0" or not records:
        raise ValueError("incomplete or empty calendar")
    output, week = [], None
    for fields in records:
        if not all(k in fields for k in ("UID", "DTSTART", "DTEND", "SUMMARY")):
            raise ValueError("missing lesson fields")
        uid, uid_params = fields["UID"]
        if uid_params or not uid or len(uid) > 1024 or any(ord(c) < 33 or ord(c) > 126 for c in uid):
            raise ValueError("invalid calendar UID")
        begin = parse_time(*fields["DTSTART"], zone)
        end = parse_time(*fields["DTEND"], zone)
        if not timedelta(0) < end - begin <= timedelta(hours=12):
            raise ValueError("invalid lesson duration")
        local_zone = ZoneInfo(zone)
        start_local, end_local = begin.astimezone(local_zone), end.astimezone(local_zone)
        current_week = week_of(begin, zone)
        if week is None:
            week = current_week
        if current_week != week or week_of(end - timedelta(seconds=1), zone) != week:
            raise ValueError("multiple calendar weeks in a file")
        if uid in seen:
            raise ValueError("duplicate lesson UID")
        seen.add(uid)
        title = clean_text(fields["SUMMARY"][0], 200)
        if not title.strip():
            raise ValueError("empty lesson title")
        location = clean_text(fields.get("LOCATION", ("", {}))[0], 240)
        description = clean_text(fields.get("DESCRIPTION", ("", {}))[0], 900)
        status = fields.get("STATUS", ("CONFIRMED", {}))[0]
        if status not in ("CONFIRMED", "TENTATIVE", "CANCELLED"):
            raise ValueError("invalid calendar event status")
        if status == "CANCELLED":
            continue
        external_id = "v1:" + sha256((current_week + "\0" + uid).encode()).hexdigest()
        body = f"{start_local:%d.%m.%Y %H:%M}–{end_local:%H:%M}"
        if location:
            body += "\n" + location
        if description:
            body += "\n" + description
        output.append(Event(SERVICE, ACCOUNT, external_id, "calendar.lesson", begin,
                            ACCOUNT, title, body,
                            {"week_start": week, "date_local": start_local.date().isoformat(),
                             "time_local": f"{start_local:%H:%M}–{end_local:%H:%M}",
                             "location": location, "timezone": zone, "provenance": provenance}))
    # A file containing only cancelled events cannot silently clear a week.
    if not output:
        raise ValueError("empty calendar snapshot")
    return week, tuple(sorted(output, key=lambda event: (event.timestamp, event.external_id)))
