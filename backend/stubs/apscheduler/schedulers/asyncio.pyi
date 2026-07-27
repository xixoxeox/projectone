from collections.abc import Awaitable, Callable
from typing import TypeVar

_Result = TypeVar("_Result")

class AsyncIOScheduler:
    def __init__(self, *, timezone: str) -> None: ...
    @property
    def running(self) -> bool: ...
    def add_job(
        self,
        func: Callable[[], Awaitable[_Result]],
        trigger: str,
        *,
        id: str,
        hour: int,
        minute: int,
        replace_existing: bool,
        max_instances: int,
        coalesce: bool,
    ) -> object: ...
    def start(self) -> None: ...
    def shutdown(self, wait: bool = True) -> None: ...
