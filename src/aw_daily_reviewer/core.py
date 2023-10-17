# ruff: noqa: TD001, TD002, TD003, FIX002
"""The logic for getting data from ActivityWatch."""
import datetime as dt
import re

import aw_core
import aw_transform
from aw_client.client import ActivityWatchClient

system_timezone = dt.datetime.now().astimezone().tzinfo


class AWDailyReviewerError(Exception):
    """Errors in the ActivityWatch daily reviewer application."""


# TODO: When the browser is the active application, fall back on the browser watcher if it exists.
# TODO: Figure out why this produces overlapping events sometimes.
class ActivityWatchCleaner:
    """Retrive and clean activity watch data."""

    def __init__(self, client: ActivityWatchClient):
        self.client = client

        self.buckets = self.client.get_buckets()

    def format_event_text(self, event: aw_core.Event) -> str:
        match event.data:
            case {"app": app, "title": title}:
                return f"{app}: {title}"
            case {"message": message}:
                return f"afk: {message}"
            case {"status": status}:  # raw AFK event.
                return str(status)
            case _:
                msg = f"Unidentified event: {event}"
                raise AWDailyReviewerError(msg)

    def get_matching_bucket_id(self, regex: str):
        match [bucket for bucket in self.buckets if re.search(regex, bucket)]:
            case []:
                msg = f"Could not find a bucket matching '{regex}'."
                raise AWDailyReviewerError(msg)
            case [bucket]:
                return bucket
            case multiple:
                msg = f"Found multiple window buckets matching '{regex}': {multiple}."
                raise AWDailyReviewerError(msg)

    def get_sorted_events(self, bucket_regex: str, start_time: dt.datetime, end_time: dt.datetime | None = None):
        return aw_transform.sort_by_timestamp(
            self.client.get_events(self.get_matching_bucket_id(bucket_regex), start=start_time, end=end_time)
        )

    def get_afk_events(self, start_time: dt.datetime, end_time: dt.datetime | None = None):
        events = aw_transform.period_union(
            [e for e in self.get_sorted_events("afk", start_time, end_time) if e.data["status"] == "afk"], []
        )
        for e in events:
            e.data["status"] = "afk"
        return events

    def get_collapsed_events(
        self, start_time: dt.datetime, end_time: dt.datetime | None = None, reduce_time: float = 60
    ):
        window_events = self.get_sorted_events("window", start_time, end_time)
        afk_events = self.get_afk_events(start_time, end_time)
        ask_away_events = self.get_sorted_events("ask-away", start_time)

        merged_events = aw_transform.union_no_overlap(afk_events, window_events)
        merged_events = aw_transform.union_no_overlap(ask_away_events, merged_events)

        reduced_events = aw_transform.heartbeat_reduce(merged_events, reduce_time)
        reduced_events = [e for e in reduced_events if e.duration.seconds > reduce_time]
        # Reduce again after filtering out small events.
        reduced_events = aw_transform.heartbeat_reduce(reduced_events, reduce_time)

        return reduced_events


if __name__ == "__main__":
    with ActivityWatchClient("aw-daily-reviewer") as client:
        cleaner = ActivityWatchCleaner(client)
        now = dt.datetime.now(tz=system_timezone)
        events = cleaner.get_collapsed_events(now - dt.timedelta(days=1), now, reduce_time=30)
        for e in events:
            start = e.timestamp.astimezone(system_timezone).strftime("%I:%M%P")
            end = (e.timestamp + e.duration).astimezone(system_timezone).strftime("%I:%M%P")
            print(start, end, int(e.duration.total_seconds() // 60), cleaner.format_event_text(e), sep="\t\t")
