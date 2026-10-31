"""What may leave the hub, decided per item.

Four flags, from most open to most closed. They are set per item, not per account, because the
same person is happy to publish their skills and never their phone number:

| flag      | in a search | a connection request | who moves first |
| --------- | ----------- | -------------------- | --------------- |
| `public`  | yes         | granted at once      | either side     |
| `confirm` | yes         | waits for the owner's yes | either side |
| `push`    | **no**      | cannot be requested  | the owner only  |
| `never`   | no          | never                | nobody          |

`push` is the interesting one: the item exists, the hub holds it, and no amount of searching will
surface it. The owner pushes it to someone they chose. It is how you keep something available
without making it askable.

Two flags meet whenever an item is read: the entity's default and the item's own. The stricter of
the two wins, always, so loosening an account default can never quietly open an item that was
closed. Nothing here grants access on its own; it says what the hub is allowed to consider.
"""

from __future__ import annotations

PUBLIC = "public"
CONFIRM = "confirm"
PUSH = "push"
NEVER = "never"

#: Ordered open to closed. The index is the strictness, which is what makes `max` the whole rule.
ORDER: tuple[str, ...] = (PUBLIC, CONFIRM, PUSH, NEVER)
DEFAULT = CONFIRM  # an item that says nothing is not public by accident

#: Flags whose items a search may return at all.
SEARCHABLE = frozenset({PUBLIC, CONFIRM})


class SharingError(ValueError):
    """An unknown sharing flag."""


def strictness(flag: str) -> int:
    """How closed a flag is, as its position in ORDER. Higher is more closed."""
    try:
        return ORDER.index(flag)
    except ValueError as exc:
        raise SharingError(f"unknown sharing flag: {flag!r}; expected one of {', '.join(ORDER)}") from exc


def resolve(entity_default: str | None, item_flag: str | None) -> str:
    """The flag that actually applies: the stricter of the entity's default and the item's own.

    Either may be missing, in which case the other decides; if both are missing the item is
    `confirm`, never `public`. The stricter-wins rule is deliberate — a person who opens their
    account default must not discover that it unsealed an item they had closed by hand.
    """
    flags = [f for f in (entity_default, item_flag) if f]
    if not flags:
        return DEFAULT
    return max(flags, key=strictness)


def searchable(entity_default: str | None, item_flag: str | None) -> bool:
    """Whether a search is allowed to return this item at all."""
    return resolve(entity_default, item_flag) in SEARCHABLE


def needs_confirmation(entity_default: str | None, item_flag: str | None) -> bool:
    """Whether a connection to this item waits for the owner's yes."""
    return resolve(entity_default, item_flag) == CONFIRM


def connectable(entity_default: str | None, item_flag: str | None) -> bool:
    """Whether another agent may ask to connect. False for `push`: the owner has to move first."""
    return resolve(entity_default, item_flag) in (PUBLIC, CONFIRM)


def pushable(entity_default: str | None, item_flag: str | None) -> bool:
    """Whether the owner may send this item to someone of their choosing."""
    return resolve(entity_default, item_flag) != NEVER


def redact(item: dict, entity_default: str | None) -> dict | None:
    """An item as a searcher may see it, or None when it may not be seen at all.

    The flag travels with the item so an agent knows whether asking is worth it, and `confirm`
    items say so rather than pretending to be freely available.
    """
    flag = resolve(entity_default, item.get("sharing"))
    if flag not in SEARCHABLE:
        return None
    return {**{k: v for k, v in item.items() if k != "sharing"}, "sharing": flag, "needs_confirmation": flag == CONFIRM}
