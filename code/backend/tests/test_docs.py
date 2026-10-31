"""The team docs stay impersonal: the pitch has roles, not people, and the team page counts heads instead of naming them."""

from pathlib import Path

DOCS = Path(__file__).resolve().parents[3] / "documentation"
ROLES = {"Speaker A", "Speaker B", "Speaker C", "Driver"}


def _rows(text: str, first_header: str) -> list[list[str]]:
    """Body rows of the first markdown table whose header starts with `first_header`."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"| {first_header} |"))
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def test_pitch_script_names_roles_not_people():
    pitch = (DOCS / "PITCH.md").read_text()
    speakers = {row[1] for row in _rows(pitch, "Time")}
    leads = {row[3] for row in _rows(pitch, "Beat")}
    assert speakers <= ROLES
    assert leads <= ROLES | {f"{role} + driver" for role in ROLES}


def test_team_page_counts_heads_without_names_or_skills():
    team = (DOCS / "TEAM.md").read_text()
    assert "10 people" in team
    header = next(line for line in team.splitlines() if line.startswith("| # | Workstream |"))
    assert "People" not in header
