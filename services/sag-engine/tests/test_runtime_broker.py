from __future__ import annotations

from sag_video.runtime import PostgreSQLRuntimeBroker


class FakePublisher:
    def __init__(self) -> None:
        self.closed = False
        self.calls: list[tuple[str, tuple[str, str]]] = []

    def execute(self, statement: str, parameters: tuple[str, str]) -> None:
        self.calls.append((statement, parameters))

    def close(self) -> None:
        self.closed = True


def test_postgres_broker_publishes_sanitized_wake_and_closes(monkeypatch):
    publisher = FakePublisher()
    monkeypatch.setattr(PostgreSQLRuntimeBroker, "_listen", lambda self: self._closed.wait())
    monkeypatch.setattr(PostgreSQLRuntimeBroker, "_connect", staticmethod(lambda _url: publisher))
    broker = PostgreSQLRuntimeBroker("postgresql://test")
    broker.notify({"project_id": "demo", "access_token": "must-not-leak"})
    assert broker.generation == 1
    assert publisher.calls[0][0] == "SELECT pg_notify(%s, %s)"
    assert "must-not-leak" not in publisher.calls[0][1][1]
    assert "[redacted]" in publisher.calls[0][1][1]
    broker.close()
    assert publisher.closed is True


def test_postgres_broker_keeps_local_wakeup_when_notify_fails(monkeypatch):
    monkeypatch.setattr(PostgreSQLRuntimeBroker, "_listen", lambda self: self._closed.wait())

    def fail(_url: str):
        raise OSError("database unavailable")

    monkeypatch.setattr(PostgreSQLRuntimeBroker, "_connect", staticmethod(fail))
    broker = PostgreSQLRuntimeBroker("postgresql://unavailable")
    broker.notify({"project_id": "demo"})
    assert broker.generation == 1
    assert broker._publisher is None
    broker.close()
