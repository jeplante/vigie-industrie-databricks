from types import SimpleNamespace

import pytest

from vigie_databricks.app_lifecycle import ensure_app_running


def app(app_state, compute_state):
    return SimpleNamespace(app_status=SimpleNamespace(state=app_state), compute_status=SimpleNamespace(state=compute_state))


class FakeApps:
    def __init__(self, states):
        self.states, self.started, self.gets = list(states), [], 0

    def get(self, name):
        self.gets += 1
        return self.states[min(self.gets - 1, len(self.states) - 1)]

    def start(self, name):
        self.started.append(name)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def run(states, **kwargs):
    apps, clock = FakeApps(states), Clock()
    client = SimpleNamespace(apps=apps)
    return apps, ensure_app_running(client, "vigie-gold-viewer", sleep=clock.sleep, clock=clock, **kwargs)


def test_running_app_is_left_untouched():
    apps, result = run([app("RUNNING", "ACTIVE")])
    assert result.action == "already_running" and apps.started == []


def test_stopped_app_is_started_and_awaited():
    apps, result = run([app("UNAVAILABLE", "STOPPED"), app("UNAVAILABLE", "STARTING"), app("RUNNING", "ACTIVE")])
    assert apps.started == ["vigie-gold-viewer"]
    assert result.action == "started" and result.waited_seconds == 20


def test_starting_app_is_awaited_without_a_second_start():
    apps, result = run([app("UNAVAILABLE", "STARTING"), app("RUNNING", "ACTIVE")])
    assert apps.started == [] and result.action == "started"


def test_timeout_raises_with_the_last_observed_state():
    with pytest.raises(TimeoutError, match="compute=STARTING"):
        run([app("UNAVAILABLE", "STOPPED"), app("UNAVAILABLE", "STARTING")], timeout_seconds=30)
