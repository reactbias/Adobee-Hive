"""Set up a business's own node, and publish its signed card to a hub.

A node is the ordinary backend with its own database, holding one card and that card's signing key. Two steps,
because the node's address has to be on the card before the node starts:

    python tools/hotel_node.py --card ../../testdata/hotel-node/hotel-lindenhof.json \
        --db data/hotel.duckdb --mcp-url http://host:8430/mcp/
    SEED_ON_EMPTY=false DUCKDB_PATH=data/hotel.duckdb uvicorn app.main:app --port 8430
    python tools/hotel_node.py --card ... --db data/push.duckdb --from-node http://host:8430 --hub http://host:8420

The second call reads the card from the running node and hands it to the hub as signed. The private key stays in
the node's database. A hub with OWNER_EDIT_TOKEN set needs that token in this process's environment.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def prepare(card_path: Path, db_path: Path, mcp_url: str) -> dict:
    """Sign the card into the node's database, with the node's address on it. Run before the node starts."""
    os.environ["DUCKDB_PATH"] = str(db_path)
    os.environ["DATABASE_URL"] = ""
    from app import db, hive, removals

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db.init()
    hive.init()
    removals.init()
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["contact"] = {**card.get("contact", {}), "mcp": mcp_url}
    current = hive.get_record(card["id"])
    if current and (current["data"].get("contact") or {}).get("mcp") == mcp_url:
        published = hive.get_card(card["id"])  # already this address: no new version to sign
    else:
        published = hive.publish(card)
    db.close()
    return published


def push(node: str, hub: str, card_id: str, token: str) -> dict:
    """Read the signed card from the node and give it to the hub, which stores it as signed."""
    card = httpx.get(f"{node.rstrip('/')}/api/hive/cards/{card_id}", timeout=10).raise_for_status().json()
    trust = card.pop("trust")
    answer = httpx.post(
        f"{hub.rstrip('/')}/api/hive/cards/signed",
        json={"card": card, "signature": trust["signature"], "public_key": trust["public_key"]},
        headers={"X-Owner-Token": token} if token else {},
        timeout=10,
    )
    if answer.status_code != 200:
        raise SystemExit(f"The hub refused the card: {answer.status_code} {answer.text}")
    return answer.json()


def main() -> None:
    """Prepare the node's database, or push its card to a hub when --from-node and --hub are given."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--card", type=Path, required=True, help="the unsigned card, as JSON")
    parser.add_argument("--db", type=Path, help="the node's DuckDB file (prepare)")
    parser.add_argument("--mcp-url", help="the address agents reach this node on (prepare)")
    parser.add_argument("--from-node", help="the running node's base URL (push)")
    parser.add_argument("--hub", help="the hub's base URL (push)")
    args = parser.parse_args()
    card_id = json.loads(args.card.read_text(encoding="utf-8"))["id"]
    if args.from_node and args.hub:
        done = push(args.from_node, args.hub, card_id, os.environ.get("OWNER_EDIT_TOKEN", ""))
        print(f"{card_id} is on {args.hub}, version {done['version']}, signed by its own key")
    elif args.db and args.mcp_url:
        done = prepare(args.card, args.db, args.mcp_url)
        print(f"{card_id} is signed in {args.db}, version {done['version']}")
    else:
        parser.error("give --db and --mcp-url to prepare, or --from-node and --hub to push")


if __name__ == "__main__":
    main()
