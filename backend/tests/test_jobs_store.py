import time

from app.jobs import store
from app.jobs.models import Job
from app.jobs.store import JobCache, cache_key, dedupe


def test_dedupe_merges_across_sources():
    a = Job("naukri", "1", "Data Analyst ", "ACME Pvt. Ltd", "Pune, Maharashtra", "u1", description="long text here")
    b = Job("foundit", "9", "data  analyst", "Acme Pvt Ltd", "pune", "u2")
    out = dedupe([b, a])
    assert len(out) == 1 and out[0].source == "naukri" and out[0].also_on == ["foundit"]


def test_dedupe_keeps_different_jobs():
    a = Job("naukri", "1", "Data Analyst", "Acme", "Pune", "u1")
    b = Job("naukri", "2", "Data Analyst", "Acme", "Mumbai", "u2")
    assert len(dedupe([a, b])) == 2


def test_dedupe_is_idempotent():
    a = Job("naukri", "1", "Data Analyst", "Acme", "Pune", "u1", description="x")
    b = Job("foundit", "9", "Data Analyst", "Acme", "Pune", "u2")
    once = dedupe([a, b])
    assert dedupe(once)[0].also_on == ["foundit"]


def test_cache_roundtrip_and_expiry(tmp_path, monkeypatch):
    c = JobCache(tmp_path / "sub" / "c.sqlite", ttl_seconds=10)
    now = time.time()
    c.put("k", [{"title": "x"}])
    assert c.get("k") == [{"title": "x"}]
    monkeypatch.setattr(store.time, "time", lambda: now + 11)
    assert c.get("k") is None
    assert c.get("missing") is None


def test_cache_key_ignores_order_and_case():
    assert cache_key({"titles": ["B", "a"], "location": "Pune"}) == \
        cache_key({"titles": ["A", "b"], "location": "pune "})
