"""Log completed domain operations after their transaction context has exited."""

import functools
import logging
import time

log = logging.getLogger("gumabot.events")


def audited(operation):
    @functools.wraps(operation)
    async def wrapped(*args, **kwargs):
        started = time.monotonic()
        status = "ok"
        try:
            return await operation(*args, **kwargs)
        except BaseException:
            status = "error"
            raise
        finally:
            log.info(
                "Domain operation",
                extra={
                    "event": "domain_operation",
                    "operation": operation.__qualname__,
                    "status": status,
                    "duration_ms": (time.monotonic() - started) * 1000,
                },
            )

    return wrapped
