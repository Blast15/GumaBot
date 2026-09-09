"""Log completed domain operations after their transaction context has exited."""

import functools
import logging

log = logging.getLogger("gumabot.events")


def audited(operation):
    @functools.wraps(operation)
    async def wrapped(*args, **kwargs):
        result = await operation(*args, **kwargs)
        log.info("Completed %s", operation.__qualname__)
        return result

    return wrapped
