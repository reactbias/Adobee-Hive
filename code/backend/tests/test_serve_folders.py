"""`tools/serve_folders.py` hands another team's agent three real folders, and withholds the rest.

Two promises are tested here, and the second one is the product's central one:

1. The three folders exist, are unlike each other, and hold real non-markdown files — the whole
   point of the fixture is an agent facing PDFs, photos and price lists rather than tidy JSON.
2. **Nothing an owner marked `private`, `shared` or `hidden` leaves the process.** Not by its path,
   not through a traversal, and not a single byte of its contents anywhere in any served response.
   A fixture that leaks a private file would demonstrate the opposite of what this repo claims.

The served set is asserted to equal the set the hub itself publishes a path for in a Card's
`structure`, so the fixture and the Card can never disagree about which file is private.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str):
    """Load one of the scripts in tools/ as a module; they are scripts, not part of the app package."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def serve():
    """tools/serve_folders.py."""
    return _module("serve_folders")


@pytest.fixture(scope="module")
def seed():
    """tools/seed_vaults.py, which owns the visibility rule the server has to honour."""
    return _module("seed_vaults")


@pytest.fixture(scope="module")
def served(serve):
    """The three default vaults, running on a port the OS picked, torn down after the module."""
    vaults = serve.load(serve.DEFAULT_VAULTS)
    httpd = serve.make_server(vaults, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.socket.getsockname()[1]}"
    try:
        yield base, vaults
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def get(url: str) -> tuple[int, bytes]:
    """Fetch a URL and return its status and body; a 4xx is an answer here, not an exception."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - our own loopback server
            return response.status, response.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


# ---------------------------------------------------------------- the three folders


def test_the_three_folders_exist_and_are_unlike_each_other(serve, seed):
    """Three real folders, on three different hubs, of three different kinds."""
    assert len(serve.DEFAULT_VAULTS) == 3
    for name in serve.DEFAULT_VAULTS:
        assert (serve.VAULTS / name).is_dir(), f"{name} is not a folder in testdata/vaults"
        assert (serve.VAULTS / name / "visibility.md").exists(), f"{name} has no visibility.md to honour"
    assert len({seed.HOME[name] for name in serve.DEFAULT_VAULTS}) == 3, "all three sit on the same hub"
    assert len({seed.KIND[name] for name in serve.DEFAULT_VAULTS}) == 3, "all three are the same kind of entity"


def test_each_folder_serves_real_non_markdown_files(served):
    """An agent that only ever sees markdown is not being tested. Each folder has a spread."""
    _, vaults = served
    for vault in vaults:
        kinds = vault.kinds
        assert kinds.get("md", 0) >= 2, f"{vault.name} has almost no prose"
        assert sum(count for ext, count in kinds.items() if ext != "md") >= 3, f"{vault.name} is markdown only"
        assert kinds.get("pdf", 0) >= 1, f"{vault.name} serves no PDF"
    spread = {ext for vault in vaults for ext in vault.kinds}
    assert {"md", "pdf", "png", "csv"} <= spread, f"the three folders between them only hold {spread}"


def test_the_served_set_is_exactly_what_a_card_publishes_a_path_for(served, seed):
    """The fixture and the Card agree, file for file: no second definition of what is private."""
    _, vaults = served
    for vault in vaults:
        from_card = {
            row["path"] for row in seed.read_structure(vault.path) if row["visibility"] in seed.OPEN_VISIBILITIES
        }
        assert set(vault.served) == from_card, f"{vault.name} serves a different set than its Card lists"


# ---------------------------------------------------------------- what must not leave


def withheld_files(vault, seed) -> list[Path]:
    """Every file in a vault the owner's rules keep out of the served set."""
    rules = seed.read_visibility(vault.path)
    return [
        f
        for f in vault.path.rglob("*")
        if f.is_file() and seed.visibility_of(f.relative_to(vault.path).as_posix(), rules)[0] not in vault.allowed
    ]


def test_every_folder_actually_withholds_something(served, seed):
    """A visibility test over folders that hide nothing would pass for the wrong reason."""
    _, vaults = served
    for vault in vaults:
        assert withheld_files(vault, seed), f"{vault.name} withholds nothing, so it tests nothing"


def test_a_withheld_path_answers_404(served, seed):
    """Asked for by name — the way an agent would guess it from a Card's own rows — it is not there."""
    base, vaults = served
    for vault in vaults:
        for file in withheld_files(vault, seed):
            relative = file.relative_to(vault.path).as_posix()
            status, _ = get(f"{base}/{vault.name}/{relative}")
            assert status == 404, f"{vault.name}/{relative} answered {status}, not 404"


def test_no_byte_of_a_withheld_file_appears_in_anything_served(served, seed):
    """The strong form: not the path, not the contents, not in a listing, not in another file."""
    base, vaults = served
    pages = [get(f"{base}/")[1], *(get(f"{base}/{v.name}/")[1] for v in vaults)]
    pages += [get(f"{base}/{v.name}/{p}")[1] for v in vaults for p in v.served]
    whole = b"\n".join(pages)
    for vault in vaults:
        for file in withheld_files(vault, seed):
            relative = file.relative_to(vault.path).as_posix()
            for line in file.read_bytes().splitlines():
                if len(line.strip()) < 8:
                    continue  # a CSV header line like "nr,monat" is not what the owner is hiding
                assert line.strip() not in whole, f"a line of {relative} was served"
            # The path, not the bare basename: `2026.csv` is a substring of a published
            # `preise-2026.csv` in another folder, which is a coincidence and not a leak.
            assert relative.encode() not in whole, f"the path {relative} was served"


def test_a_private_folder_is_a_count_and_nothing_else(served):
    """`private` admits to how much, exactly as the Card does, and never to what."""
    base, vaults = served
    anker = next(v for v in vaults if v.name == "wirtshaus-anker")
    assert anker.counted == {"gaeste/": 2}, anker.counted
    page = get(f"{base}/wirtshaus-anker/")[1].decode()
    assert "gaeste/" in page and "2 file(s)" in page
    assert "anreisen" not in page, "a private file was named"
    # `buchhaltung/` is `hidden`: not served, not counted, not mentioned under any flag.
    assert "buchhaltung" not in page, "a hidden folder was mentioned"
    assert "buchhaltung/" not in anker.counted


def test_traversal_and_a_vault_that_is_not_served(served):
    """The allowlist is a dict of exact paths, so nothing on disk can be reached around it."""
    base, _ = served
    for path in (
        "wirtshaus-anker/../jonas-brun/projekte/offerten.csv",
        "wirtshaus-anker/..%2f..%2fetc%2fpasswd",
        "wirtshaus-anker/gaeste/",
        "hotel-krafft/about.md",
        "no-such-vault/about.md",
    ):
        status, _ = get(f"{base}/{path}")
        assert status == 404, f"{path} answered {status}, not 404"


def test_strict_serves_only_public(serve, seed):
    """`--strict` is the finer line in cards/README.md: `public` contents are the ones for a stranger."""
    vaults = serve.load(serve.DEFAULT_VAULTS, serve.STRICT_VISIBILITIES)
    for vault in vaults:
        assert vault.served, f"{vault.name} serves nothing at all under --strict"
        rules = seed.read_visibility(vault.path)
        for relative in vault.served:
            assert seed.visibility_of(relative, rules)[0] == "public"
        assert "about.md" not in vault.served, "public-summary leaked into the strict set"


# ---------------------------------------------------------------- what it says on the way up


def test_the_banner_names_each_folder_its_url_and_what_is_in_it(serve):
    """Startup has to be enough to point an agent at this without reading the source."""
    vaults = serve.load(serve.DEFAULT_VAULTS)
    text = serve.banner(vaults, "127.0.0.1", 8600, serve.OPEN_VISIBILITIES)
    for vault in vaults:
        assert f"http://127.0.0.1:8600/{vault.name}/" in text
        assert vault.title in text
        assert vault.summary() in text
    assert "public-summary" in text
    assert "404" in text, "the banner does not say what happens to a withheld path"


def test_the_index_links_every_folder_and_says_it_is_fictional(served):
    """A crawler starts at / and has to be able to find all three, and to be told what this is."""
    base, vaults = served
    status, body = get(f"{base}/")
    assert status == 200
    page = body.decode()
    for vault in vaults:
        assert f'href="/{vault.name}/"' in page
    assert "real business" in page


def test_head_decides_the_same_as_get(served, seed):
    """An agent may check a path before fetching it, and must get the same answer."""
    base, vaults = served
    vault = vaults[0]
    served_path = sorted(vault.served)[0]
    hidden = withheld_files(vault, seed)[0].relative_to(vault.path).as_posix()
    for relative, expected in ((served_path, 200), (hidden, 404)):
        request = urllib.request.Request(f"{base}/{vault.name}/{relative}", method="HEAD")  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                assert response.status == expected
                assert response.read() == b""
        except urllib.error.HTTPError as err:
            assert err.code == expected


def test_a_file_is_served_byte_for_byte_with_its_real_media_type(served):
    """A PDF has to arrive as a PDF: an agent decides how to parse a file by what it is told."""
    base, _ = served
    status, body = get(f"{base}/elektro-mattenhof/preisliste.pdf")
    assert status == 200
    assert body.startswith(b"%PDF-"), "the PDF did not arrive as a PDF"
    assert body == (ROOT.parents[1] / "testdata/vaults/elektro-mattenhof/preisliste.pdf").read_bytes()
    with urllib.request.urlopen(f"{base}/elektro-mattenhof/preisliste.pdf", timeout=10) as response:  # noqa: S310
        assert response.headers["Content-Type"] == "application/pdf"


def test_the_documented_defaults_are_the_real_ones(serve):
    """`documentation/SEARCH_API.md` prints the port and host, so they are pinned here."""
    assert serve.DEFAULT_PORT == 8600, "SEARCH_API.md names this port"
    assert serve.DEFAULT_HOST == "127.0.0.1", "a fixture that binds every interface by default is a surprise"
    assert serve.DEFAULT_VAULTS == ("wirtshaus-anker", "jonas-brun", "elektro-mattenhof")
