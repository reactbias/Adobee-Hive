"""Second use of the Hive: companies looking for people."""

import pytest

from app import nl_query


def test_seeded_candidates_and_funnel(client):
    assert len(client.get("/api/candidates").json()) == 60
    funnel = client.get("/api/funnel").json()
    assert sum(s["count"] for s in funnel) == 60


def test_mock_query_filters(client):
    out = client.post("/api/query", json={"question": "Python developers in Basel with 3+ years"}).json()
    assert out["mode"] == "mock"
    for row in out["rows"]:
        assert "Python" in row["skills"] and row["years_experience"] >= 3 and "Basel" in row["location"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM candidates",
    "SELECT raw_text FROM cv_documents",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT 1; SELECT 2",
    "SELECT data FROM profiles",
])
def test_unsafe_sql_is_blocked(sql):
    with pytest.raises(nl_query.UnsafeQuery):
        nl_query.validate(sql)


def test_cv_text_is_parsed(client):
    cv = "Jane Doe\nData Engineer\nBased in: Basel\n6 years Python, SQL and AWS. German, English. jane@example.com"
    out = client.post("/api/cvs/text", json={"text": cv}).json()
    assert out["full_name"] == "Jane Doe"
    assert {"Python", "SQL", "AWS"} <= set(out["skills"])


def test_person_card_only_shares_visible_fields(client):
    client.put("/api/profiles/t1", json={"display_name": "Tobi", "about": "secret", "visibility": {
        "headline": True, "skills": True, "about": False, "location": True, "projects": True}})
    client.post("/api/profiles/t1/connectors/github")
    card = client.post("/api/profiles/t1/publish").json()
    assert card["kind"] == "person" and card["description"] == ""
    assert "python" in card["features"]
    assert card["trust"]["signature_valid"]
