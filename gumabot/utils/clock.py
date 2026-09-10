from datetime import UTC, datetime


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def timestamp(self) -> int:
        return int(self.now().timestamp())
