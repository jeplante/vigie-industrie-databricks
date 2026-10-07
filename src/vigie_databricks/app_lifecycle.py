"""Start the App before the operations monitor checks it; never alters its code or data."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable


@dataclass(frozen=True)
class AppStartResult:
    action: str  # "already_running" or "started"
    waited_seconds: float


def _state(status: Any) -> str:
    return str(getattr(status, "state", "") or "").split(".")[-1]


def is_available(app: Any) -> bool:
    return _state(getattr(app, "app_status", None)) == "RUNNING" and _state(getattr(app, "compute_status", None)) == "ACTIVE"


def ensure_app_running(
    client: Any,
    app_name: str,
    *,
    timeout_seconds: float = 600,
    poll_seconds: float = 10,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> AppStartResult:
    """Start a stopped App and wait until it is RUNNING; leave a running App untouched."""
    app = client.apps.get(app_name)
    if is_available(app):
        return AppStartResult("already_running", 0.0)
    started = clock()
    if _state(getattr(app, "compute_status", None)) in {"STOPPED", "ERROR"}:
        client.apps.start(app_name)
    while clock() - started < timeout_seconds:
        sleep(poll_seconds)
        app = client.apps.get(app_name)
        if is_available(app):
            return AppStartResult("started", clock() - started)
    raise TimeoutError(
        f"{app_name} not available after {timeout_seconds:.0f}s: "
        f"app={_state(getattr(app, 'app_status', None))}, compute={_state(getattr(app, 'compute_status', None))}"
    )
