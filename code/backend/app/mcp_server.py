"""The Hive as an MCP server: the "homepage" an AI agent visits instead of a website.

Mounted at /mcp (Streamable HTTP). Any MCP client can connect, e.g. Claude Desktop,
Claude's MCP connector, or our own agent in app/agent.py.
"""

from collections.abc import Mapping
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import (
    admin,
    config,
    connections,
    domains,
    folder_keys,
    guard,
    hive,
    hub,
    limits,
    owner,
    registration,
    rulesets,
    waiting,
)

server = MCPServer(
    name="Adobee Hive",
    instructions=(
        "Adobee Hive is a federation of hubs, each carrying signed, agent-facing business cards. This hub is "
        f"{config.HIVE_HUB_ID}: {config.HIVE_DESCRIPTION} "
        "It is not the whole Hive. Its peers carry other places and other trades, so a search that finds nothing "
        "here may still find it one hop out: pass radius 1 (or up to 3) to hive_discover, and use hub_directory "
        "to see which hubs exist, what each carries and which are taking members. "
        "Use hive_discover to find anyone by what they offer or need — a hotel, a developer, a café — "
        "with kind as a filter and looking_for to say which side of the market you are on; hive_get_card to read "
        "one card and "
        "verify its Ed25519 signature, hive_check_availability before booking, and hive_book to complete a booking. "
        "Only state facts that come from cards. Tell the user why you picked a business (score_breakdown, why) "
        "and keep the booking receipt: it is needed to cancel or to leave a verified review. "
        "If nothing fits and the user wants to be told, hive_wait leaves an anonymous standing request. "
        "To reach a person rather than book a room, use hub_connect: some entries open at once and some wait "
        "for their owner's yes. After the real meeting has happened, hub_score records how it actually went, "
        "which is the only thing that teaches this Hive which other Hives to believe. "
        "If the person you work for is on this Hive themselves, their entry is yours to look after: "
        "hive_owner_card reads it as they see it, hive_owner_propose turns what they tell you into a diff, and "
        "hive_owner_publish signs that diff into the live card once they have said yes to it."
    ),
)


_safe = domains.safe


def _counted(out: dict[str, Any], kind: str) -> dict[str, Any]:
    """Count an agent's call against the card it touched, so its owner sees it; errors count for nothing."""
    card_id = out.get("card_id") or out.get("id")
    if "error" not in out and card_id:
        hive.record_event(card_id, kind, "agent")
    return out


@server.tool()
def hive_discover(
    ctx: Context,
    query: str = "",
    kind: str | None = None,
    near: str | None = None,
    max_price_chf: float | None = None,
    features: list[str] | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int = 1,
    ruleset: str | None = None,
    radius: int = 0,
    looking_for: str = "offers",
    limit: int | None = None,
    include_irrelevant: bool = False,
) -> dict[str, Any]:
    """Find anyone in the Hive by what they offer or what they need: a hotel, a developer, a café.

    looking_for: which side of the market you are on. "offers" (the default) finds whoever provides the thing,
    "needs" finds whoever wants what you provide, "any" finds both. Every result says whether it is claimed by
    its subject and whether it is bookable: an unclaimed card was compiled from public information, so it can
    only be handed off to the business's own site after the user says yes, and nothing on it can be booked.
    kind: a filter, not a gate — hotel | cafe | person | event and whatever else this hub holds.
    near: a landmark such as 'basel sbb', 'messe basel', 'marktplatz', 'badischer bahnhof'.
    features: exact tags such as 'dog-friendly', 'late check-in', 'quiet', 'breakfast', 'parking'.
    Dates are ISO (YYYY-MM-DD). Returns ranked matches with score_breakdown and why, plus excluded
    businesses with why_not, so you can explain the choice to the user.
    ruleset: only one your user chose (see hive_rulesets). The answer names it and what it changed; tell the user.
    radius: how far to look. 0 (the default) is this Hive only. 1 also asks its peer Hives, 2 their peers, up to 3.
    Above 0 each match says in provenance which hubs it travelled and how many hops, and its score_breakdown adds
    local_relevance, hub_path_trust and hop_decay; tell the user when a business came from another Hive. A radius
    above 0 makes this hub call its peers, so it is rate-limited: a refusal names the budget and when to retry.
    limit: how many matches to answer with, up to 50. The answer says `truncated` and `total_matches` when there
    were more, so narrow the query or raise this rather than assuming you saw the whole Hive.
    A match from another Hive carries that business's full signed card inline under `card`, already verified
    against its owner's key: read it from there rather than calling hive_get_card again, and pass it to
    hub_connect when you connect. hive_get_card also works for such an id, by asking the peer.
    The answer carries `matched` (how many businesses the query actually earned something from) over
    `considered` (how many were ranked to get them). Only the ones that earned something come back, so
    `matched: 0` means nothing on this Hive answers the question — say so to the user rather than offering
    the closest row, and consider hive_wait. Do not threshold on `score > 0` yourself: reputation is paid on
    every query, so a few well-reviewed businesses score 1-2 on everything, including nonsense.
    include_irrelevant: ask for the unfiltered ranking too, including businesses that matched nothing.
    """
    if radius and (over := guard.admit_mcp(guard.federated, ctx, charge_in_process=True)):
        return {"error": over}  # the budget the REST route spends, before this hub calls any peer
    found = _safe(
        hive.discover,
        query,
        kind,
        near,
        max_price_chf,
        features,
        check_in,
        check_out,
        guests,
        radius,
        looking_for=looking_for,
    )
    if "error" not in found and ruleset:
        found = _safe(rulesets.apply, found, ruleset)
    if "error" in found:
        return found
    # Threshold first, then cap. The other way round the ceiling would spend its 20 slots on businesses
    # the query earned nothing from and cut the ones it did — and at radius 2 every match carries a full
    # inline card, so those rows are the expensive ones too (73 matches came to 690 KB, ~65 scoring zero).
    found = hive.only_relevant(
        found,
        hive.asks_anything(query, features, near, max_price_chf),
        include_irrelevant,
    )
    return limits.bound_answer(found, limit)


@server.tool()
def hive_what_was_promised(receipt: str) -> dict[str, Any]:
    """Show the signed card version a booking was made against (prices, policies), and which fields changed since.
    Use it when the stay differs from what was booked. Verify the old card against the owner's pinned key."""
    return _safe(hive.what_was_promised, receipt)


@server.tool()
def hive_rulesets() -> dict[str, Any]:
    """List the rulesets a user can choose for hive_discover, each signed by its author (keys in
    /.well-known/hive.json under ruleset_keys). A ruleset only narrows results; it never boosts a business."""
    return rulesets.catalogue()


@server.tool()
def hive_get_card(ctx: Context, card_id: str, radius: int = 1) -> dict[str, Any]:
    """Read one business's full Hive card: offering, units and prices, policies, contact, and trust
    (signature, public key, third-party attestations, proof-of-stay reviews).

    Works for an id this Hive found on a peer: if it does not carry the card itself it asks its peers for
    it, and the answer says in `trust.federation` which Hive it came from. radius 0 looks only at this Hive.
    A federated match from hive_discover already carries the same signed card inline under `card`, so you
    do not have to call this at all for a result you have just been handed — use that and save the hop."""
    local = _safe(hive.get_card, card_id)
    if "error" not in local or not radius:
        return _counted(local, "read")
    if over := guard.admit_mcp(guard.federated, ctx, charge_in_process=True):
        return {"error": over}
    found = hive.card_from_peer(card_id, radius)
    return _counted(found, "read") if found else local


@server.tool()
def hive_check_availability(card_id: str, check_in: str, check_out: str, guests: int = 1) -> dict[str, Any]:
    """List the units (rooms) free for these ISO dates and guest count, cheapest first, with totals in CHF."""
    return _counted(_safe(hive.check_availability, card_id, check_in, check_out, guests), "checked")


@server.tool()
def hive_book(
    card_id: str,
    unit_id: str,
    check_in: str,
    check_out: str,
    guest_name: str,
    guests: int = 1,
    notes: str = "",
    agent: str = "MCP agent",
) -> dict[str, Any]:
    """Book a unit. Only call this after the user has agreed to the business, room, dates and price.
    Returns a confirmation with a signed receipt (keep it for cancel and review)."""
    return _safe(hive.book, card_id, unit_id, check_in, check_out, guest_name, guests, notes, agent)


@server.tool()
def hive_cancel(booking_id: str, receipt: str) -> dict[str, Any]:
    """Cancel a booking. Requires the signed receipt returned by hive_book."""
    return _safe(hive.cancel, booking_id, receipt)


@server.tool()
def hive_review(receipt: str, rating: int, text: str) -> dict[str, Any]:
    """Leave a verified review (1-5) for a stay. Requires the booking's signed receipt."""
    return _safe(hive.review, receipt, rating, text)


@server.tool()
def hive_wait(
    check_in: str,
    check_out: str,
    features: list[str] | None = None,
    near: str | None = None,
    max_price_chf: float | None = None,
    guests: int = 1,
) -> dict[str, Any]:
    """When hive_discover found nothing that fits, and only if your user wants to be told: leave an anonymous
    standing request. If a business later changes its signed card to fit, it sends a signed offer. Returns a
    request_id and a secret token; keep both. Never include the user's name or words."""
    return _safe(waiting.leave, features, near, max_price_chf, check_in, check_out, guests)


@server.tool()
def hive_check_waiting(request_id: str, token: str) -> dict[str, Any]:
    """Check a standing request. Offers are signed by the business; verify them against its pinned key and ask
    your user before booking with hive_book."""
    return _safe(waiting.check, request_id, token)


# The stays tools above came first; every other use case registers its tools from app/domains.
domains.register_all(server)


def http_app():
    """Return the MCP server as an ASGI app for Streamable HTTP, mounted at /mcp."""
    # Behind the hosting proxy the Host header is the public domain, so host checks are off;
    # the MCP surface only exposes public card data and actions that don't reveal private data.
    return server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


@server.tool()
def hub_connect(
    requester: str,
    entity_id: str,
    ctx: Context,
    requester_hub: str = "",
    target_hub: str = "",
    via_hub: str = "",
    card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ask to be introduced to a business or person found in a search, and log the introduction.

    An entry marked public opens at once; one marked `needs_confirmation` waits for its owner's yes; one its
    owner shares only on their own initiative cannot be asked for at all. Returns the connection and its state.
    Keep the connection id: it is what hub_score needs later.

    For an entity on **another** hub, pass the signed `card` the federated search returned for it and
    `target_hub`, the hub id its provenance names. This hub verifies that card against the key that hub pinned
    for it and refuses it otherwise; an introduction to a remote entity is recorded here and its owner's yes,
    if it needs one, happens on their own hub.

    `requester_hub` is the hub your person is a member of, if it is not this one. Pass it and the row records it
    as a **claim**: this hub cannot check it, and the answer's `requester_proof` says `claimed` so nobody reads
    it as more than that. Leave it out and the row says `none`. It is never filled in with this hub's own id,
    because a visitor who said nothing is not a member — which is what the ledger used to record.

    Verifying a card from a peer means fetching that peer's key registry, so this spends the same budget
    `POST /api/hub/connect` spends; a refusal names it and says when to try again.

    Ask **your own** hub for an introduction to something a peer carries, rather than going to the peer and
    asserting a name there. This hub then tells the peer on your behalf, so the peer knows a member of another
    hub asked and the row this hub will learn from stays here, where the search found the match — a score weeks
    later is the only evidence a hub ever gets about a peer, and one recorded somewhere else is evidence this
    hub did the work for and lost. The answer's `forwarded` says what the peer made of it; a peer that cannot
    be reached changes nothing about the introduction recorded here. Nothing stops you walking to the peer
    instead: `hub_directory` gives you every peer's URL. It just costs this hub the record."""
    if over := guard.admit_mcp(guard.federated, ctx, charge_in_process=True):
        return {"error": over}  # refused before this hub fetches any peer's key registry
    return _safe(
        hub.connect,
        requester,
        entity_id,
        requester_hub=requester_hub,
        target_hub=target_hub,
        via_hub=via_hub,
        card=card,
    )


@server.tool()
def hub_score(ctx: Context, connection_id: str, rating: int, note: str = "") -> dict[str, Any]:
    """Record how an introduction actually went, after the real meeting, from the person who asked for it.

    `rating` is tenths of a star out of five: 43 means 4.3 stars. Scoring is once and final, and only while the
    connection is still open — an introduction nobody scored within a month closes unscored. This is the only
    input to how much this Hive trusts the Hive the entry came from, so ask the person, never guess.

    The score belongs to whoever asked for the introduction, so this needs **their** credential: the link secret
    `hub_connect` returned in `folder_key.secret`, put in this connection's `Authorization: Bearer <secret>`
    header. It is a header and not an argument for the reason the owner token is — an argument is written into
    this conversation and into your client's logs. A connection id is not a credential: it is in the answer that
    made it and in `hub_connections`, and knowing one used to be enough to spend somebody else's one score."""
    return _safe(hub.score, connection_id, rating, note, secret=_link_secret(ctx))


@server.tool()
def hub_connections(requester: str = "") -> dict[str, Any]:
    """List introductions still waiting on somebody: on an owner's yes, or on the person's score.

    Use it to ask "how did it go with X?" before the connection goes stale and can no longer be scored. Each row
    says how long it has left as well as when it runs out: `stale_in_days` counts whole days, 0 meaning today is
    the last one, and `stale_soon` flags an open introduction with a week or less to go. An introduction nobody
    scores closes unscored and is then worth nothing to anybody — a score after the real meeting is the only
    evidence this Hive ever gets about the Hive an entry came from — so take a `stale_soon` row first. A request
    still waiting on an owner's yes carries its own shorter window in `stale_in_days` and no flag."""
    return {
        "awaiting_rating": connections.awaiting_rating(requester),
        "awaiting_confirmation": connections.pending_confirmation(),
    }


@server.tool()
def hub_standing() -> dict[str, Any]:
    """What this Hive makes of its neighbours, from how their ratings held up against real meetings.

    `error` is published minus realised, in tenths of a star: lower is better, negative means the Hive
    undersold what it offered. A Hive with too little evidence is reported as unproven rather than guessed at."""
    return hub.standing()


@server.tool()
def hub_registration() -> dict[str, Any]:
    """Read what this Hive asks of someone who wants to join, before writing an application.

    Returns the admission policy, the checks an application goes through, the proof types accepted, and an
    example document. Read this first: a hub may be invite-only or closed, and the answer says so."""
    return registration.policy()


@server.tool()
def hub_register(
    entity: dict[str, Any],
    ctx: Context,
    public_key: str = "",
    proofs: list[dict[str, Any]] | None = None,
    invite: str = "",
    signature: str = "",
) -> dict[str, Any]:
    """Apply to join this Hive on behalf of your user, with one signed JSON document.

    `entity` is the card: id, kind, name, description, sharing. Bring a `public_key` and your user keeps the
    private half — sign the canonical JSON of the whole application except `signature` to prove they hold it.
    Omit the key and this Hive generates and holds one, which is weaker and is recorded as such.

    A refusal is an answer, not a failure: the reply always carries the checks, the reason and what to do next.
    Never invent proofs — they are claims about the world and a hub that catches a false one will block you.

    An application is signature-checked and stored, so this spends the same budget `POST /api/hub/register`
    spends; a refusal for being over it names the budget and says when to try again."""
    if over := guard.admit_mcp(guard.federated, ctx, charge_in_process=True):
        return {"error": over}  # refused before the application is verified or stored
    return _safe(
        registration.apply,
        {"entity": entity, "public_key": public_key, "proofs": proofs or [], "invite": invite, "signature": signature},
    )


# ---------------------------------------------------------------- the owner's own three tools
#
# The owner's credential rides the **transport**, in the same `X-Owner-Token` header the REST routes
# read, and never an argument: an argument is written into the agent's transcript, into its client's
# tool log and into whatever the model keeps of the turn, and a shared secret in four places is not
# one. `mcp==2.3.0` hands a tool its request headers through `Context.headers`, so the header is
# readable without leaving the protocol. On a transport that carries no headers at all — stdio, or
# this repo's own in-process agent — the token arrives empty and the edit tools refuse, which is the
# right way round.


def _link_secret(ctx: Context | None) -> str:
    """The folder link secret this call carried, or "". Compared and dropped, never logged or echoed.

    A link secret is a party's own credential for one introduction (`folder_keys.py`), which is what
    makes it the right proof for a score: it names *which side* of the row the caller is, where the
    hub's owner token would only say somebody on this hub may act.
    """
    headers: Mapping[str, str] = (ctx.headers if ctx else None) or {}
    value = next((v for k, v in headers.items() if k.lower() == folder_keys.HEADER.lower()), "")
    return folder_keys.bearer(value)


def _owner_token(ctx: Context) -> str:
    """The owner token this call carried, or "". Header names are compared without regard to case.

    Nothing else ever reads it, nothing logs it and no tool puts it in an answer: it is compared
    against this hub's secret in constant time (`guard.secret_matches`) and dropped.
    """
    headers: Mapping[str, str] = ctx.headers or {}
    return next((v for k, v in headers.items() if k.lower() == owner.TOKEN_HEADER.lower()), "")


def _refused_edit(ctx: Context) -> dict[str, Any] | None:
    """The refusal an owner edit gets when this call carries no usable owner token, else None."""
    refused = owner.editable(_owner_token(ctx))
    return {"error": refused} if refused else None


@server.tool()
def hive_owner_card(card_id: str, ctx: Context) -> dict[str, Any]:
    """Read one card the way its owner sees it, which is more than hive_get_card shows anybody else.

    On top of the signed card: the bookings it has taken or the hand-offs it has made, the demand it was in the
    running for and lost (`missed_demand`, the asks it did not fit), what agents did with it over the last seven
    days (`last_7_days`), and the standing requests waiting for a change like the one you may be about to make.

    Read it before proposing anything: `missed_demand` is the list of sentences the card could have answered and
    did not, and it is the best evidence you will get for what to change. Needs no token — a guest's name comes
    through as initials ("M. K.") unless this connection carries the owner's, and nothing else is withheld.
    """
    return _safe(owner.overview, card_id, _owner_token(ctx))


@server.tool()
def hive_owner_propose(card_id: str, instruction: str, ctx: Context) -> dict[str, Any]:
    """Turn a plain-language change to your person's own card into a proposed card and a diff. Publishes nothing.

    Say what changed the way they said it to you — "dogs are welcome now, and the standard double is 150" — in
    any of English, German, French or Italian. You get back `proposed` (the whole card as it would be), `changes`
    (one row per field, with `before` and `after`), and a one-line `summary`. The card on the hub is untouched:
    show `changes` to your person, in their words, and ask. `hive_owner_publish` is the yes.

    `mode` in the answer says who did the editing. A hub with no model key falls back to a rule-based editor and
    answers `mock`: it understands "add <tag>", "remove <tag>" and "<room name> <price>" in those four
    languages and nothing else, so read `changes` rather than assuming the instruction was understood — an empty
    `changes` means it was not, and the `summary` says so.

    `description` is the card's pitch to agents like you, so write it for discovery: say what the business
    actually offers, in the words someone would search for. Nothing here reads it for tone — the only thing that
    can refuse it is its size.

    Needs the owner token on this connection (the `X-Owner-Token` header). A change that would pass one of this
    hub's published ceilings (`hub_registration` lists all 24) is refused here, naming the ceiling and the size
    that passed it, rather than looking fine and failing at publish. id, slug and kind cannot be changed at all.
    """
    if refused := _refused_edit(ctx):
        return refused
    if config.LLM_ENABLED and (over := guard.over_budget(guard.llm_calls, f"owner:{card_id}")):
        return {"error": over}  # the same model budget the REST route spends, counted per card
    out = _safe(owner.propose, card_id, instruction)
    if "error" in out:
        return out
    if too_big := owner.refusal(out["proposed"]):
        return {"error": f"This hub will not publish that change: {too_big}. Shorten it and propose again."}
    return out


@server.tool()
def hive_owner_publish(card_id: str, proposed: dict[str, Any], ctx: Context) -> dict[str, Any]:
    """Publish the card hive_owner_propose returned, once your person has seen the diff and said yes.

    Pass `proposed` back exactly as you received it. The hub re-signs it with the owner's key and gives it the
    next version number, so the agent that reads it next verifies the new card against the key pinned for this id
    in `/.well-known/hive.json` — a published change that no longer verifies would be worse than no change at
    all, so the signature is never carried over. id, slug and kind keep the values they have, whatever the
    proposal says, and the old versions are kept so an existing booking can still show what it was promised.

    Returns the published card with its new `trust.signature` and `version`, and sends a signed offer to anyone
    whose standing request this change now fits. Needs the owner token on this connection (the `X-Owner-Token`
    header): without it nothing is published. Do not call it on a diff nobody agreed to.
    """
    if refused := _refused_edit(ctx):
        return refused
    return _safe(owner.apply, card_id, proposed)


@server.tool()
def hub_directory(ctx: Context) -> dict[str, Any]:
    """List the Hives this one knows of, so a user can choose which to join before applying.

    Every row carries an absolute `url` and an absolute `apply_at`, including this hub's own, so a row can be
    read out to a person as an address that works. A hub nobody has scored an introduction through reads
    `verdict: "unproven"` with the count so far; `verdict_meanings` says what each verdict means and `why` says
    it for that hub, so "unproven" can be passed on as "no evidence either way" rather than as a warning.

    Each row says whether it is taking members, what it asks of them, and how closely its published ratings
    have matched what real people found: `error` is published minus realised, and lower is better."""
    # This hub's own address, from the headers this call arrived on when nothing is configured: the same
    # address the caller already reached, which is the one that works for them. Never a guess at a hostname —
    # and `HIVE_PUBLIC_URL` is the override for a deployment where the scheme or the host is rewritten in front
    # of this process, because `x-forwarded-proto` is only as good as the proxy that sets it.
    headers: Mapping[str, str] = {k.lower(): v for k, v in (ctx.headers or {}).items()}
    host = headers.get("host", "")
    scheme = headers.get("x-forwarded-proto", "").split(",")[0].strip() or "http"
    return admin.directory(f"{scheme}://{host}" if host else "")
