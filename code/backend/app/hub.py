"""The hub as something an agent talks to: search it, ask to be connected, score it afterwards.

Three stores sit behind this: the index (hive.py), the neighbours (federation.py) and the manual
blocklist (blocklist.py). This module is the door they are reached through, and the only place the
four of them are composed.

What an agent can do:

- `search` the index, across peer Hives at a chosen radius, getting JSON back. Items the owner
  closed never appear, and blocked hubs and entities are filtered on the way in and on the way out.
- `connect` to something it found, **on this hub or on a peer**. The two agents' folders link first
  (folders.py) and the answer carries the manifest that link opened; then a `public` item opens at
  once, a `confirm` item waits for the owner's yes, and a `push` item cannot be asked for at all.
  Either way the introduction is logged. An entity this hub does not carry is connected to on the
  strength of the signed card the search returned, verified here against the key its *own* hub
  pinned — never on the carrier's word.
- `score` the introduction afterwards, once the human has actually met whoever it was.

That last step is what everything else is built on. The hub learns nothing useful from a search and
nothing trustworthy from a booking; it learns from a person saying, weeks later, how it went.
"""

from __future__ import annotations

from typing import Any

from . import blocklist, calibration, config, connections, folder_keys, folders, hive, sharing


class HubError(ValueError):
    """A hub request that cannot be served as asked."""


def _entity_default(card: dict[str, Any]) -> str:
    """The sharing flag an entity applies to everything it holds, unless an item is stricter.

    One line, because `hive.sharing_default` is the answer and this is the name the rest of this
    module and `admin.py` already call it by. It moved there when `discover` had to obey it too: a
    rule the search path cannot reach is a rule the search path does not follow.
    """
    return hive.sharing_default(card)


def _published_rating(card: dict[str, Any]) -> int | None:
    """What this hub says the entity is worth, in tenths of a star, for later honesty checking.

    Frozen here on purpose. Honesty is measured against what was claimed at the introduction, not
    against whatever the hub is claiming by the time a human gets round to scoring it.
    """
    rating = card.get("rating")
    if rating is None:
        rating = ((card.get("trust") or {}).get("verified_reviews") or {}).get("average")
    return None if rating is None else int(round(float(rating) * 10))


def visible(match: dict[str, Any]) -> bool:
    """Whether a result may be shown at all: not blocked, and not closed by its owner."""
    if blocklist.is_blocked(blocklist.ENTITY, str(match.get("id") or "")):
        return False
    route = ((match.get("provenance") or {}).get("path")) or []
    if route and blocklist.filter_path([str(h) for h in route]):
        return False
    return sharing.searchable(match.get("sharing"), match.get("item_sharing"))


async def search(ask: dict[str, Any], radius: int = 0) -> dict[str, Any]:
    """Search the index and, above radius 0, the neighbours. Returns JSON an agent can act on.

    Every match says whether connecting to it needs the owner's yes, so an agent can tell the
    difference between something it can have now and something it has to ask for.
    """
    from . import federation  # local: federation imports hive, and hive must load first

    found = await federation.search(ask, radius=radius) if int(radius or 0) > 0 else _local(ask)
    out = []
    for match in found.get("matches") or []:
        if not visible(match):
            continue
        flag = sharing.resolve(match.get("sharing"), match.get("item_sharing"))
        out.append(
            {
                **match,
                "sharing": flag,
                "needs_confirmation": flag == sharing.CONFIRM,
                "connectable": sharing.connectable(match.get("sharing"), match.get("item_sharing")),
            }
        )
    return {**found, "matches": out, "hub": config.HIVE_HUB_ID}


def _local(ask: dict[str, Any]) -> dict[str, Any]:
    """A radius-0 search, kept separate so the async path above reads as one thing."""
    return hive.discover(**ask)


def _verified_remote(entity_id: str, offered: Any, target_hub: str) -> dict[str, Any]:
    """A card for an entity this hub does not carry, or a refusal that names why it was not taken.

    An introduction is the *local* hub's to record even when the entity is not its own: a person on
    this hub asking to meet somebody in Bern is a fact this hub should store. What it must not do is
    take the asker's word for who that somebody is, so the card arrives with the request and is
    checked here exactly as a relayed search result is (`federation._verified`): the pinning key
    comes from the entity's **own** hub's registry, which this hub fetched itself in the background
    from a URL on its own peer list. Nothing about the key comes from the request.

    A card that cannot be checked is refused, never admitted with a note. That is the one thing
    federation does not bend on, and an unverifiable stranger is exactly the case the rule is for.
    """
    from . import federation  # local: federation imports hive, and hive must load first

    if not isinstance(offered, dict) or not offered:
        raise HubError(
            f"{entity_id} is not on this hub. An introduction to an entity on a peer needs the signed card the"
            " search returned for it, passed as `card`, plus `target_hub`: this hub verifies it against the key"
            " that entity's own hub pinned rather than trusting whoever carried it"
        )
    if str(offered.get("id") or "") != entity_id:
        raise HubError(
            f"the card offered is for {str(offered.get('id') or '')!r}, not for {entity_id!r};"
            " a connection is made to the entity whose card was checked"
        )
    if not target_hub:
        raise HubError(
            f"{entity_id} is not on this hub, so an introduction to it needs `target_hub`: the hub id the search"
            " said it came from, which is where its pinned key is read from"
        )
    pins = federation.pinned_keys_of(target_hub)
    if not pins:
        raise HubError(
            f"this hub has no key registry for {target_hub!r}, so {entity_id}'s card cannot be checked here and is"
            f" refused rather than trusted. Either {target_hub} is not on this hub's peer list, or it has not"
            " answered yet — a fresh hub takes up to PEER_ASK_SECONDS to learn its neighbours' keys"
        )
    if not hive.verify_pinned(offered, pins):
        raise HubError(
            f"the card offered for {entity_id} is not the one {target_hub} published for it: unsigned, altered, or"
            f" signed by a key {target_hub} does not pin for it. Refused rather than trusted"
        )
    return offered


def connect(
    requester: str,
    entity_id: str,
    *,
    requester_hub: str = "",
    target_hub: str = "",
    via_hub: str = "",
    card: Any = None,
) -> dict[str, Any]:
    """Ask to be introduced to something, on this hub or on a peer, and log the introduction.

    Refused outright for a blocked entity, for a blocked hub, and for an item its owner marked
    `push` or `never` — those are the owner's to send, not anyone's to request. An entity this hub
    does not carry needs its signed card and its hub id with the request; see `_verified_remote`.
    """
    entity_id = (entity_id or "").strip()
    if not entity_id:
        raise HubError("a connection needs an entity to connect to")
    if blocklist.is_blocked(blocklist.ENTITY, entity_id):
        raise HubError(f"{entity_id} is blocked on this hub")
    if target_hub and blocklist.is_blocked(blocklist.HUB, target_hub):
        raise HubError(f"{target_hub} is blocked on this hub")

    record = hive.get_record(entity_id)
    # Local first, and the local copy wins: a card this hub carries itself is the one it answers for.
    held = record["data"] if record is not None else _verified_remote(entity_id, card, target_hub)
    remote = record is None
    flag = sharing.resolve(_entity_default(held), None)
    if not sharing.connectable(flag, None):
        raise HubError(
            f"{entity_id} cannot be asked for: its owner shares it only on their own initiative"
            if flag == sharing.PUSH
            else f"{entity_id} is not shared"
        )

    # The folders meet before the booking does. A published, freely connectable Card is a standing
    # yes to being contacted — that is what publishing one means — so its link is accepted in the
    # same step. A `confirm` Card's owner has said nothing yet, so its link waits for the same
    # moment they confirm the introduction. Either way the link opens no contents: that needs a
    # grant, which is the owner's to give (folders.py).
    who, them = folders.handle_for(requester), folders.handle_for(entity_id)
    link = folders.open_link(who, them, auto_accept=flag == sharing.PUBLIC, by=them)
    published = _published_rating(held)
    row = connections.request(
        requester,
        entity_id,
        requester_hub=requester_hub or config.HIVE_HUB_ID,
        target_hub=target_hub,
        via_hub=via_hub or target_hub,
        sharing=flag,
        published_rating=published,
        needs_confirmation=flag == sharing.CONFIRM,
        folder_link=link["id"],
    )
    # The requester asked to be introduced, so this answer speaks for the requester and may hand it
    # the credential for its side of the link: `folder_key.secret` is the only time that secret
    # exists outside a hash, and it reads nothing the owner has not granted. A `confirm` Card's link
    # is still `requested` here, so there is no key to give yet — it is minted when the owner says
    # yes, which is `connections.confirm`'s moment and not this one.
    key = folder_keys.mint(link["id"], who) if link["state"] == folders.ESTABLISHED else None
    out = {**row, "folder": folders.manifest(them, who), "folder_key": key}
    if remote:
        # Said in the answer, not only in the row: an introduction to somebody on another hub is one
        # this hub recorded and cannot complete. Its owner's yes happens where its owner is, and
        # `connections.confirm` refuses it here for the same reason (`folder` is empty for the same
        # reason again — the entity's folder is on its own hub, not on this disk).
        out["remote"] = True
        out["origin_hub"] = target_hub
        out["says"] = (
            f"{entity_id} is carried by {target_hub}, not by this hub. Its card was checked against the key"
            f" {target_hub} pinned for it. This hub has recorded the introduction"
            + (
                f"; {entity_id}'s owner says yes on {target_hub}, not here."
                if flag == sharing.CONFIRM
                else " and opened it."
            )
        )
    return out


def score(connection_id: str, rating: int, note: str = "") -> dict[str, Any]:
    """Score an introduction after the real meeting, and show what it did to the hub it came from.

    This is the only moment the trust layer learns anything, so the answer says plainly what the
    score changed: the gap against what was promised, and where that leaves the carrying hub.
    """
    row = connections.rate(connection_id, rating, note)
    hub_id = row.get("via_hub") or row.get("target_hub") or ""
    published = row.get("published_rating")
    out: dict[str, Any] = {"connection": row, "hub": hub_id}
    if hub_id and published is not None:
        gap = calibration.delta(published, row["rating"])
        out["gap"] = gap
        out["gap_stars"] = round(gap / 10, 2)
        out["says"] = (
            f"{hub_id} promised {connections.stars(published)} and you found {row['rating_stars']}"
            if gap
            else f"{hub_id} had it exactly right"
        )
        out["hub_standing"] = calibration.trust(hub_id)
    return out


def standing() -> dict[str, Any]:
    """What this hub currently thinks of its neighbours. The admin GUI's main table."""
    return {"hub": config.HIVE_HUB_ID, "peers": calibration.ranked()}
