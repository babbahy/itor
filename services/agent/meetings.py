from datetime import timedelta, timezone
from typing import Protocol

from .models import Meeting, MeetingInput, utc_now
from .storage import Store


class MeetingProvider(Protocol):
    def upcoming(self) -> list[Meeting]: ...
    def get(self, meeting_id: str) -> Meeting | None: ...


class DemoMeetingProvider:
    def __init__(self, store: Store):
        self.store = store
        if not self.upcoming():
            self.reset()

    def upcoming(self) -> list[Meeting]:
        now = utc_now()
        meetings = self.store.list("demo_meeting", Meeting)
        return sorted((item for item in meetings if item.end_at > now), key=lambda item: item.start_at)

    def get(self, meeting_id: str) -> Meeting | None:
        return self.store.get("demo_meeting", meeting_id, Meeting)

    def reset(self) -> list[Meeting]:
        start = utc_now().replace(second=0, microsecond=0)
        examples = [
            ("Product Team Weekly", 12, 30, "Microsoft Teams", "Review priorities and share one update."),
            ("Project Review", 110, 45, "Zoom", "Have the project milestones ready to discuss."),
            ("Customer Sync", 1450, 30, "Google Meet", "Review open questions before the call."),
        ]
        meetings = []
        with self.store.connect() as db:
            db.execute("DELETE FROM records WHERE bucket='demo_meeting'")
            for title, offset, duration, platform, notes in examples:
                date = start + timedelta(minutes=offset)
                meeting = Meeting(title=title, start_at=date, end_at=date + timedelta(minutes=duration),
                                  platform=platform, notes=notes, source="demo")
                self.store.put("demo_meeting", meeting.id, meeting, db=db)
                meetings.append(meeting)
        return meetings


class LocalMeetingProvider:
    def __init__(self, store: Store, demo: MeetingProvider):
        self.store = store
        self.demo = demo

    def upcoming(self) -> list[Meeting]:
        now = utc_now()
        with self.store.connect() as db:
            rows = db.execute("""
                SELECT payload FROM records
                WHERE bucket='meeting' AND julianday(json_extract(payload, '$.end_at')) > julianday(?)
                ORDER BY julianday(json_extract(payload, '$.start_at')) LIMIT 100
                """, (now.isoformat(),)).fetchall()
        meetings = [Meeting.model_validate_json(row[0]) for row in rows]
        return sorted([*self.demo.upcoming(), *meetings], key=lambda item: item.start_at)

    def get(self, meeting_id: str) -> Meeting | None:
        return self.store.get("meeting", meeting_id, Meeting) or self.demo.get(meeting_id)

    def add(self, request: MeetingInput) -> Meeting:
        start = request.start_at.astimezone(timezone.utc)
        meeting = Meeting(
            title=request.title, start_at=start,
            end_at=start + timedelta(minutes=request.duration_minutes), platform=request.platform,
            join_url=request.join_url, notes=request.notes, source="manual",
        )
        self.store.put("meeting", meeting.id, meeting)
        return meeting
