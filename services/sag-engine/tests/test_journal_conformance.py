from __future__ import annotations

import json
from pathlib import Path

import pytest

from sag_video.journal import InadmissibleJournalPayload, JournalEntryRequest, SagJournalService
from sag_video.store import Store


FIXTURES = Path(__file__).resolve().parents[3] / "contracts/x1/sqlite3-sag-journal-fixtures.json"
FREEZE_FIXTURES = Path(__file__).resolve().parents[3] / "contracts/x1/journal-freeze-fixtures"


def assert_subset(actual: dict, expected: dict) -> None:
    assert {key: actual.get(key) for key in expected} == expected


@pytest.mark.parametrize("fixture", json.loads(FIXTURES.read_text())["fixtures"], ids=lambda entry: entry["name"])
def test_independent_adapter_matches_sqlite3_sag_fixture_hashes(tmp_path: Path, fixture: dict):
    store = Store(tmp_path / f"{fixture['name']}.db")
    journal = SagJournalService(store)
    namespace = fixture["chain"]["ns"]
    for raw in fixture["inputs"]:
        journal.append(namespace, JournalEntryRequest.model_validate({
            "tags": [], "metadata": {}, "method": "manual", "hash_alg": fixture["chain"]["alg"], **raw,
        }))
    with store.transaction():
        for mutation in fixture.get("tamper", []):
            for column, value in mutation["set"].items():
                assert column in {"content", "kind", "method", "created_at"}
                store._connection.execute(
                    f"UPDATE sag_journal_entries SET {column}=? WHERE namespace=? AND seq=?",
                    (value, namespace, mutation["seq"]),
                )
        for seq in fixture.get("delete_seq", []):
            store._connection.execute(
                "DELETE FROM sag_journal_entries WHERE namespace=? AND seq=?", (namespace, seq),
            )
    rows = [entry.model_dump(mode="json") for entry in journal.entries(namespace, limit=100)]
    assert len(rows) == fixture["expected"]["count"]
    for actual, expected in zip(rows, fixture["expected"]["rows"]):
        assert_subset(actual, expected)
    assert_subset(journal.verify(namespace), fixture["expected"]["verify"])
    store.close()


def test_journal_api_uses_scope_uri_and_refuses_undeclared_or_inadmissible_payloads(client):
    contract = client.get("/api/contract").json()
    assert contract["journal_protocol_version"] == "sag-journal/0.1-draft"
    assert "JournalEntryRequest" in contract["journal_schemas"]
    assert {"RRFSourceEvidence", "ContextNodeReceipt", "ContextLoadReceipt"} <= set(contract["x1_context_schemas"])
    body = {
        "id": "journal-api-entry-0001", "kind": "sag.receipt", "content": "release approval committed",
        "created_at": "2026-07-24T12:00:00+00:00", "metadata": {"revision": 1},
    }
    first = client.post("/api/projects/demo/journal/entries", json=body)
    repeated = client.post("/api/projects/demo/journal/entries", json=body)
    assert first.status_code == 201 and first.json()["inserted"] is True
    assert repeated.status_code == 201 and repeated.json()["inserted"] is False
    assert first.json()["entry"]["namespace"] == "sag://sag-video/project/demo/project/demo"
    verification = client.get("/api/projects/demo/journal/verify").json()["verification"]
    assert verification["ok"] is True and verification["checked"] == 1
    unknown = client.post("/api/projects/demo/journal/entries", json={**body, "id": "unknown-kind", "kind": "undeclared"})
    assert unknown.status_code == 409
    fractional = client.post("/api/projects/demo/journal/entries", json={
        **body, "id": "fractional", "metadata": {"score": 0.5},
    })
    assert fractional.status_code == 422
    secret = client.post("/api/projects/demo/journal/entries", json={
        **body, "id": "secret", "content": "-----BEGIN PRIVATE KEY-----",
    })
    assert secret.status_code == 422


@pytest.mark.parametrize("fixture_path", sorted(FREEZE_FIXTURES.glob("*.json")), ids=lambda path: path.stem)
def test_journal_adapter_reproduces_frozen_x1_fixture_set(tmp_path: Path, fixture_path: Path):
    fixture = json.loads(fixture_path.read_text())
    store = Store(tmp_path / f"{fixture['name']}.db")
    journal = SagJournalService(store)
    namespace = fixture["chain"]["ns"]
    refused = False
    for raw in fixture["inputs"]:
        try:
            journal.append(namespace, JournalEntryRequest.model_validate({
                "tags": [], "metadata": {}, "method": "manual", "hash_alg": fixture["chain"]["alg"], **raw,
            }))
        except InadmissibleJournalPayload:
            refused = True
    if fixture.get("expect_refusal"):
        assert refused is True
        assert fixture["expected"]["refused"] is True
        assert len(journal.entries(namespace, limit=100)) == fixture["expected"]["count"]
    else:
        assert refused is False
        rows = [entry.model_dump(mode="json") for entry in journal.entries(namespace, limit=100)]
        assert len(rows) == fixture["expected"]["count"]
        for actual, expected in zip(rows, fixture["expected"]["rows"]):
            assert_subset(actual, expected)
        assert_subset(journal.verify(namespace), fixture["expected"]["verify"])
    store.close()


def test_x1_context_receipt_contract_is_bounded_and_refuses_untraceable_kept_nodes():
    from sag_video.x1_context import ContextLoadReceipt, ContextNodeReceipt

    kept = ContextNodeReceipt(
        task="load endpoint context", anchor="api/main.py", path="api/main.py", title="main",
        rrf_sources=["bm25", "structural:folder", "rules"], score=0.0269, tokens=37,
        decision="kept", reason="", ts="2026-01-01T00:00:00Z",
    )
    dropped = ContextNodeReceipt(
        task="load endpoint context", anchor="api/routes.py", path="api/routes.py", title="routes",
        rrf_sources=["bm25"], score=0.0267, tokens=38, decision="dropped", reason="budget",
        ts="2026-01-01T00:00:00Z",
    )
    receipt = ContextLoadReceipt(
        task="load endpoint context", nodes=[kept, dropped], budget=40, tokens_used=37,
        total_candidates=8, would_load_blind=276, tokens_saved=239, anchors=["api/main.py"],
    )
    assert receipt.tokens_saved == 239
    with pytest.raises(ValueError):
        ContextNodeReceipt(
            task="load endpoint context", anchor="", path="api/main.py", title="main",
            rrf_sources=[], score=0.1, tokens=1, decision="kept", ts="2026-01-01T00:00:00Z",
        )
