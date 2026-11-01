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
  pinned — never on the carrier's word. Who is *asking* is the weaker half: see `requester_origin`,
  which records what the hub established rather than assuming the asker is one of its own.
- `score` the introduction afterwards, once the human has actually met whoever it was. An
  introduction to an entity this hub carries itself is scored against this hub's *own* claim about
  it, so a hub can be measured by its own members' meetings and not only by its peers'.

That last step is what everything else is built on. The hub learns nothing useful from a search and
nothing trustworthy from a booking; it learns from a person saying, weeks later, how it went.
"""

from __future__ import annotations

import base64
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from . import blocklist, calibration, config, connections, folder_keys, folders, guard, hive, owner, sharing


class HubError(ValueError):
    """A hub request that cannot be served as asked."""


def _entity_default(card: dict[str, Any]) -> str:
    """The sharing flag an entity applies to everything it holds, unless an item is stricter.

    A business card on a public hub is public. A person is `confirm` unless their card says
    otherwise (hive.CONSENT_FIRST_KINDS): an introduction to a person is theirs to grant.
    """
    fallback = sharing.CONFIRM if card.get("kind") in hive.CONSENT_FIRST_KINDS else sharing.PUBLIC
    return str(card.get("sharing") or fallback)


def _published_rating(card: dict[str, Any]) -> int | None:
    """What this hub says the entity is worth, in tenths of a star, for later honesty checking.

    Frozen here on purpose. Honesty is measured against what was claimed at the introduction, not
    against whatever the hub is claiming by the time a human gets round to scoring it.

    In practice the number is always the second lookup: no card in the index carries a top-level
    `rating`, because a rating is not a thing an owner may sign about themselves. It is
    `trust.verified_reviews.average`, computed per read from reviews that each cost a real booking
    receipt — which is why this has to be handed a `hive.get_card` body and not a stored one.
    `None` is the honest answer for an entity nobody has reviewed: nothing was claimed, so there is
    nothing a score could be measured against, and `connections.rated_via` leaves the row out.
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


def requester_origin(requester: str, claimed: str = "") -> tuple[str, str]:
    """Where the requester is from, and what that answer is worth. Never this hub by default.

    `requester_hub` used to default to `config.HIVE_HUB_ID` — the hub *receiving* the request. So an
    agent from Zurich asking Basel for an introduction was written into Basel's ledger as a Basel
    member, and nothing downstream could tell a member from a visitor from an invention. These rows
    are the input to `calibration.py`, which is what ranks a hub in federated search, so the default
    was quietly putting words in a stranger's mouth inside the trust model's own evidence (#158).

    Three answers, and the hub only ever gives the one it can stand behind:

    - **member**: this hub carries an entity with that id, so it is answering for somebody it
      already vouches for. The only one of the three that is a *check* rather than a record — and
      note what it does not prove: that the caller *is* that member. See `limits` below.
    - **claimed**: the caller named a hub. Recorded as what it is, a string, and discountable by
      anyone reading the ledger.
    - **none**: nobody said anything. The honest answer, and the one the old default replaced with a
      false one.

    `limits`: even `member` is a check on the *name*, not on the caller. This hub has no per-owner
    credential (#135), so "an entity by this id is on this hub" is the whole of what is established.
    That is why the proof is recorded on the row rather than used as a permission: a reader can
    discount a claim, but a gate built on one would be a gate that is not there.
    """
    name = (requester or "").strip()
    if name and hive.get_record(name) is not None:
        return config.HIVE_HUB_ID, connections.BY_MEMBER
    claimed = (claimed or "").strip()
    if claimed:
        return claimed, connections.BY_CLAIM
    return "", connections.BY_NOBODY


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
    remote = record is None
    # Local first, and the local copy wins: a card this hub carries itself is the one it answers for.
    #
    # `hive.get_card` and not `record["data"]`. The stored body is the card as its owner *signed* it,
    # and a signature cannot cover a number that changes every time somebody reviews the place, so
    # the trust block is computed per read and is not in the body at all. Reading the body here left
    # `_published_rating` with nothing to find on every local introduction, and a row with no
    # published claim is one `connections.rated_via` drops: the hub could never learn anything from
    # an introduction to one of its own members, and its own directory row stayed `unproven` however
    # much it was used (#164).
    #
    # This makes the two branches agree rather than adding a special case — the remote branch has
    # always received a `get_card` body, trust block included. What `held` is read for is `kind` and
    # `sharing` (`_entity_default`) and the published claim (`_published_rating`); the first two are
    # the same values in the body and in the card, so the claim is the only thing that changes.
    held = _verified_remote(entity_id, card, target_hub) if remote else hive.get_card(entity_id)
    flag = sharing.resolve(_entity_default(held), None)
    if not sharing.connectable(flag, None):
        raise HubError(
            f"{entity_id} cannot be asked for: its owner shares it only on their own initiative"
            if flag == sharing.PUSH
            else f"{entity_id} is not shared"
        )

    # An introduction to an entity this hub carries was carried *by this hub*, and that is exactly
    # the claim calibration measures: this hub said what the entity was worth, and weeks later a
    # person came back and said what they found. A blank `target_hub` attributed the row to nobody,
    # so `rated_via` and `hubs_with_ratings` both passed over it and the evidence was thrown away.
    #
    # Note which way round this is. The *target* hub of a local entity really is this hub, because
    # this hub is the one carrying it and making the claim about it. The *requester* hub is the
    # opposite case and must not be defaulted the same way: a visitor from another hub is not a
    # member of this one, whatever this hub would like to record (#158).
    if not remote and not target_hub:
        target_hub = config.HIVE_HUB_ID

    # The folders meet before the booking does. A published, freely connectable Card is a standing
    # yes to being contacted — that is what publishing one means — so its link is accepted in the
    # same step. A `confirm` Card's owner has said nothing yet, so its link waits for the same
    # moment they confirm the introduction. Either way the link opens no contents: that needs a
    # grant, which is the owner's to give (folders.py).
    who, them = folders.handle_for(requester), folders.handle_for(entity_id)
    link = folders.open_link(who, them, auto_accept=flag == sharing.PUBLIC, by=them)
    published = _published_rating(held)
    from_hub, proof = requester_origin(requester, requester_hub)
    row = connections.request(
        requester,
        entity_id,
        requester_hub=from_hub,
        requester_proof=proof,
        target_hub=target_hub,
        via_hub=via_hub or target_hub,
        sharing=flag,
        published_rating=published,
        needs_confirmation=flag == sharing.CONFIRM,
        folder_link=link["id"],
    )
    # The requester asked to be introduced, so this answer speaks for the requester and may hand it
    # the credential for its side of the link: `folder_key.secret` is the only time that secret
    # exists outside a hash, and it reads nothing the owner has not granted.
    # Minted whatever the link's state, and `pending_ok` is why. The requester asked for this
    # introduction and this answer speaks for them, so this is their one chance to be handed a
    # credential for it — and for a `confirm` Card that is the *only* chance, because the next thing
    # that happens to the row is a decision only its owner may make. A key on a link the other side
    # has not accepted reads nothing (`folder_keys.resolve` re-reads the link's state every time), so
    # what it carries here is proof of which side of this introduction the holder is, which is what
    # `hub.score` and a requester's withdrawal need (#107).
    key = folder_keys.mint(link["id"], who, pending_ok=True)
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


# ---------------------------------------------------------------- who may answer for a row
#
# Two decisions sit on a connection and they belong to two different people. The **owner** of the
# target says yes or no to being introduced, and the **requester** says afterwards how it went.
# Neither needed anything: an unrelated caller who knew a connection id could walk a row from
# `requested` through `open` to `rated`, and the real requester's score was then refused as already
# given. The id is in the answer `hub_connect` returns and in the queues an agent reads, so it was
# never a secret and was never authority (#107).
#
# What this hub has to work with is not accounts (#135 is roadmap) but three things that exist:
#
# - a **link secret** (`folder_keys.py`): 32 bytes bound to one side of one folder link, resolving to
#   a handle. Every connection row stands on a folder link, so a link secret names a *party to this
#   row* — the strongest proof here, and the only one that is per-party rather than per-hub.
#   `hub.connect` hands the requester theirs, which is why `folder_keys.mint` now mints on a pending
#   link: otherwise a `confirm` introduction had no requester-side proof in existence at all.
# - a **signed action** under the key the target registered, for a card whose owner brought one
#   (`custody: "owner"`, `owner_public_key` pinned). Per-entity and unforgeable by this hub. Same
#   shape as `registration.withdrawal_statement`.
# - this hub's **owner token**, and its **admin credential**. Both are hub-wide: they prove the
#   holder may answer for *an* entity here, never for *this* one. That is the #135 gap, and it is
#   recorded on the row rather than smoothed over, so a reader can tell a per-entity yes from a
#   hub-wide one.
#
# Every door fails closed. No proof means the row is not touched, and `decided_by` / `scored_by`
# record which of the proofs it actually was.

BY_LINK, BY_OWNER_KEY, BY_OWNER_TOKEN, BY_ADMIN = "link secret", "owner key", "owner token", "hub operator"

#: How long a signed decision is good for. Short, like `registration.WITHDRAW_WINDOW_S`, and for the
#: same reason: a window is the only thing bounding a signature somebody captured.
DECIDE_WINDOW_S = 300

DECIDE_ACTIONS = ("confirm", "decline")


def decision_statement(connection_id: str, action: str, nonce: str, expires: str) -> dict[str, Any]:
    """The exact document an owner's signed yes or no covers.

    The **connection** so a yes to one introduction is not a yes to another, the **action** so a
    decline cannot be replayed as a confirm, a **nonce** so two decisions are two documents, and an
    **expiry** so a captured signature stops working.
    """
    return {"connection": connection_id, "action": action, "nonce": nonce, "expires": expires}


def decision_to_sign(connection_id: str, action: str, nonce: str = "", expires: str = "") -> dict[str, Any]:
    """A ready-to-sign decision document and its canonical bytes, so a client signs what is checked."""
    if action not in DECIDE_ACTIONS:
        raise HubError(f"an action is one of {', '.join(DECIDE_ACTIONS)}, not {action!r}")
    nonce = (nonce or secrets.token_urlsafe(16)).strip()
    expires = (expires or (_now() + timedelta(seconds=DECIDE_WINDOW_S)).isoformat()).strip()
    statement = decision_statement(connection_id, action, nonce, expires)
    return {
        "statement": statement,
        "canonical": base64.b64encode(hive.canonical(statement)).decode(),
        "nonce": nonce,
        "expires": expires,
    }


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _expired(expires: str) -> bool:
    """True when this document's window has closed, or its expiry cannot be read.

    Unreadable counts as closed: a signature over an expiry nothing can parse has no window, and on
    a decision that cannot be taken back the safe reading of "no window" is "shut".
    """
    try:
        when = datetime.fromisoformat((expires or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is not None:
        when = when.astimezone(UTC).replace(tzinfo=None)
    return when <= _now()


def _party_by_link(row: dict[str, Any], secret: str, who: str) -> bool:
    """True when `secret` is a live key for `who`'s side of the folder link this row stands on.

    Three things are checked and all three matter: that the secret belongs to a live key at all, that
    the key is on **this row's** link — one for some other link between the same two agents would
    otherwise do — and that the handle it names is the side being claimed.

    `folder_keys.party_of` and not `resolve`: the read door refuses a link the other side has not
    accepted, which is right for reading somebody's files and wrong here. An introduction waiting for
    its owner's yes stands on a link that is not established *by definition*, so asking the read door
    would have left the owner's own decision with nothing per-party behind it. Authority over this
    row is not access to a folder. Both calls re-read the link on every request, so revoking the link
    ends this on the next one.
    """
    if not secret or not row.get("folder_link"):
        return False
    key = folder_keys.party_of(secret)
    if key is None or key["link"] != row["folder_link"]:
        return False
    try:
        return key["handle"] == folders.handle_for(who)
    except folders.FolderError:
        return False


def _owner_signed(row: dict[str, Any], action: str, signature: str, nonce: str, expires: str) -> bool:
    """True when this decision carries a valid signature under the key the target itself registered.

    The key comes from the card in this hub's own index (`owner_public_key`, pinned at registration
    when the applicant brought one), never from the request. A card whose key this hub holds has
    none, so this is simply not available for it and the caller is told which proof it can give.
    """
    record = hive.get_record(row["target"])
    pinned = str(((record or {}).get("data") or {}).get("owner_public_key") or "")
    if not pinned:
        raise HubError(
            f"{row['target']}'s signing key is held by this hub, not by its owner, so there is no owner"
            f" signature to check. Its owner answers with this hub's {owner.TOKEN_HEADER}"
        )
    if not (signature and nonce and expires):
        raise HubError(
            "a signed decision needs `signature`, `nonce` and `expires` together: the nonce and the expiry"
            " are part of the document that was signed"
        )
    if _expired(expires):
        raise HubError(f"this decision document has expired; ask for another and sign that ({DECIDE_WINDOW_S} s)")
    if not hive.verify(decision_statement(row["id"], action, nonce, expires), signature, pinned):
        raise HubError(
            f"the signature does not match the key {row['target']} registered, or it covers a different"
            " document. It is made over the canonical JSON of {connection, action, nonce, expires}"
        )
    return True


def decide(
    connection_id: str,
    action: str,
    *,
    note: str = "",
    secret: str = "",
    owner_token: str = "",
    signature: str = "",
    nonce: str = "",
    expires: str = "",
    by_operator: str = "",
) -> dict[str, Any]:
    """The target's owner answers an introduction. Refused for anyone who cannot show they may.

    `action` is `confirm` or `decline`. The proofs, strongest first: the target's side of this row's
    folder link, a signature under the key the target registered, this hub's owner token, or the
    operator. The row records which it was, so a per-entity yes and a hub-wide one are different
    facts afterwards.

    A declining *requester* is not a case this answers. The old code let a decline through on the
    grounds that it was "this hub's own caller giving up on its own request", which was never
    checked and so was available to anybody; a requester who wants out shows the same link secret
    they would score with.
    """
    if action not in DECIDE_ACTIONS:
        raise HubError(f"an action is one of {', '.join(DECIDE_ACTIONS)}, not {action!r}")
    row = connections.get(connection_id)
    if row["state"] != connections.REQUESTED:
        raise HubError(f"only a requested connection can be answered, this one is {row['state']}")

    if _party_by_link(row, secret, row["target"]):
        proof = BY_LINK
    elif _party_by_link(row, secret, row["requester"]) and action == "decline":
        proof = f"{BY_LINK} (requester withdrew)"
    elif signature or nonce or expires:
        _owner_signed(row, action, signature, nonce, expires)
        proof = BY_OWNER_KEY
    elif owner_token and guard.secret_matches(owner_token, config.OWNER_EDIT_TOKEN):
        proof = BY_OWNER_TOKEN
    elif by_operator:
        proof = f"{BY_ADMIN} ({by_operator})"
    else:
        raise HubError(_no_authority(row, action))

    if action == "confirm":
        return connections.confirm(connection_id, decided_by=proof)
    return connections.decline(connection_id, note, decided_by=proof)


def _no_authority(row: dict[str, Any], action: str) -> str:
    """Why this decision is refused, naming the proofs this particular row can actually take."""
    record = hive.get_record(row["target"])
    signs = bool(str(((record or {}).get("data") or {}).get("owner_public_key") or ""))
    ways = [
        f"the `Authorization: Bearer <link secret>` for {row['target']}'s side of this introduction's folder link",
    ]
    if signs:
        ways.append(
            f"a signature under the key {row['target']} registered"
            f" (GET /api/hub/connections/{row['id']}/decision?action={action} returns the document)"
        )
    ways.append(
        f"this hub's {owner.TOKEN_HEADER}"
        if config.OWNER_EDIT_TOKEN
        else f"this hub's {owner.TOKEN_HEADER}, which its operator has not set"
    )
    return (
        f"{action} on {row['id']} needs authority over {row['target']}. A connection id is in the answer that"
        f" made it and in the queues anybody reads, so knowing one is not authority to act on it. This hub"
        f" accepts: {'; or '.join(ways)}. An operator can also answer, as their own act, through"
        f" POST /api/admin/connections/{row['id']}/{action}"
    )


def score(
    connection_id: str, rating: int, note: str = "", *, secret: str = "", by_operator: str = ""
) -> dict[str, Any]:
    """Score an introduction after the real meeting, and show what it did to the hub it came from.

    This is the only moment the trust layer learns anything, so the answer says plainly what the
    score changed: the gap against what was promised, and where that leaves the carrying hub.

    The score belongs to the party that asked for the introduction, and there is exactly one of
    them, so this takes the requester's own link secret — `hub.connect` returns it — and nothing
    hub-wide. An operator can score as themselves for a demo or a repair, and the row says so;
    a hub-wide credential standing in for the requester would make the one final score available to
    whoever holds it, which is the half of #107 that matters most. Fails closed either way.
    """
    row = connections.get(connection_id)
    if _party_by_link(row, secret, row["requester"]):
        proof = BY_LINK
    elif by_operator:
        proof = f"{BY_ADMIN} ({by_operator})"
    else:
        raise HubError(
            f"scoring {row['id']} needs the requester's own credential: the"
            " `Authorization: Bearer <link secret>` that the answer to the connect request returned, for"
            f" {row['requester']}'s side of this introduction's folder link. A connection id is not it — it is in"
            " that same answer and in the queues anybody reads. One introduction gets one score, and it is the"
            " person who asked for the meeting who gives it"
        )
    row = connections.rate(connection_id, rating, note, scored_by=proof)
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
