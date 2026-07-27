from collections.abc import Awaitable, Callable
from typing import Any

class AsyncIOScheduler:
    def __init__(self, *, timezone: str) -> None: ...
    @property
    def running(self) -> bool: ...
    def add_job[Result](
        self,
        func: Callable[..., Awaitable[Result]],
        trigger: str,
        *,
        id: str,
        args: list[Any] = ...,
        day_of_week: str = ...,
        hour: int = ...,
        minute: int = ...,
        replace_existing: bool = ...,
        max_instances: int = ...,
        coalesce: bool = ...,
        misfire_grace_time: int = ...,
        timezone: str = ...,
    ) -> object: ...
    def start(self) -> None: ...
    def shutdown(self, wait: bool = True) -> None: ...
