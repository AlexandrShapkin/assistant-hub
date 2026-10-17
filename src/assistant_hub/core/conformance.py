"""Reusable deterministic runtime checks; no discovery, I/O or polling here."""
from .contracts import Event, PollResult, validate_cursor


def validate_poll_result(service: str, account: str, result: PollResult,
                         previous_cursor: str | None = None) -> None:
    validate_cursor(previous_cursor)
    if not isinstance(result, PollResult) or not isinstance(result.events, tuple):
        raise ValueError("invalid poll result")
    validate_cursor(result.cursor)
    if previous_cursor is not None and result.cursor is None:
        raise ValueError("poll cannot reset an established cursor")
    for event in result.events:
        if not isinstance(event, Event):
            raise ValueError("invalid event")
        event.__post_init__()
        if event.service_id != service or event.account_id != account:
            raise ValueError("adapter spoofed event scope")
