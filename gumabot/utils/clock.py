from datetime import datetime, timezone


class Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def timestamp(self) -> int:
        return int(self.now().timestamp())
