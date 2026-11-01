# Folders: the private side of a Card

A Card says what an entity offers. A **folder** is the material behind it — the CV, the price list, the
room photos, the contract. The Card never carries that material, only its shape: `structure` lists every
file with its path, size, media type and digest, and reads the contents of markdown only.

This page is the plan for serving that material, now partly built. It says plainly which parts run and
which do not. **How to call what runs is [FOLDER_API.md](FOLDER_API.md)** — a handover page with real
responses from a hub actually started from this branch.

## What is built today

`app/folders.py` holds the whole protocol and is wired into `main.py` via `folders.init()`:

| | |
| --- | --- |
| `claim(handle)` | register a handle against a folder |
| `open_link` · `accept_link` · `get_link` · `between` · `linked` · `links` | handle-to-handle links |
| `grant(path, to_handle)` · `grants` · `can_read(path, handle)` | per-path, read-only access |
| `manifest(owner, viewer)` | what a linked viewer may see, plus a count of what is withheld |
| `files` · `visibility_of` · `digest` · `media_type` · `split_path` · `check_handle` | the mechanics |

`hub.connect` already opens a link during an introduction, accepting it in the same step for a `public`
Card, because publishing one is a standing yes to being contacted.

**It decides access and moves no bytes.** The HTTP surface over it — a caller identity, the two read
endpoints, and the grant and revoke writes — is now built; see [FOLDER_API.md](FOLDER_API.md) and the
slices below, each marked with what actually landed.

## The two layers, and why there are two

A **link** is handle to handle. It carries no content and opens only the manifest — which is where a
linked peer finally sees the `shared` files the Card never mentioned.

A **grant** is per path, read-only, the owner's to give, and is the only thing that makes bytes readable.

ClaudeConnect's own `add_friend_to_authz` collapses these into one: it grants `r` on `[/]`, the entire
context directory. One layer where this product needs two, which is why we use its protocol as
inspiration and serve folders ourselves rather than calling its server.

`private` and `hidden` files are counted, never named. A refused grant says the same words for a hidden
file as for one that never existed, because listing a file in order to say it is secret leaks it.

## The blocker is identity, not routes

`folders.py` has no notion of *who is asking*. Every other piece exists, so a read route without a caller
identity would either serve everything or nothing. That is why identity comes first.

### Slice A — a viewer identity, tied to the link · **built** (`app/folder_keys.py`)

Mint a **link secret** (32 random bytes, urlsafe), store **only its hash**, and return it once
in the accept response. Reads present it:

```
Authorization: Bearer <link_secret>   →   (link_id, viewer_handle, owner_handle)
```

The link is already the unit of trust and already revocable, so revoking a link kills its reads with it
and there is no second set of bookkeeping to keep in step. Hashed at rest, so a stolen database is not a
stolen folder. Never logged, never returned twice.

A key names a *side* of a link rather than a direction of reading, because both parties do the same two
things with one: read what the other granted, and grant from their own folder. That is what lets a grant
be a per-owner write on a hub that has no owner accounts.

Two doors hand one out, and each speaks for the party that called it: `POST /api/hub/connect`, for the
requester it names, which is how a client goes from "found her in the index" to "holding the folder" in
one call; and `POST /api/folders/keys`, which is the **operator's** door and is said plainly in
[SECURITY.md](../SECURITY.md) not to prove per-owner identity. The accept route below would be the
owner's own door and is not built, so until it is, the owner's side of a link is minted by the operator.

### Slice B — the read surface · **built**

```
GET /api/folders/status          which link is in use, what a read costs, and the honest line
GET /api/folders/manifest        the manifest for the authenticated viewer
GET /api/folders/file?path=…     the bytes, gated by can_read
```

The path travels in the query string rather than as path segments, which was a correction to the plan:
an HTTP client collapses `../` inside a URL *path* before sending it, so a traversal test against path
segments is testing the client rather than the hub. In the query it arrives exactly as written.

Both derive owner **and** viewer from the bearer and take no handle parameter, so a caller cannot ask
about a folder it has no link to and there is no enumeration surface.

This is the whole path a client needs: open a connection, get the folder, read a file. It is enough to
spawn an agent on a granted context and extract what it was sent for.

### Slice C — the driving surface · **half built**

```
POST   /api/folders/claim                   register a handle              not built
POST   /api/folders/links                   request a link                 not built
POST   /api/folders/links/{id}/accept       accept, and receive the secret not built
GET    /api/folders/links                   what this handle has           not built
GET    /api/folders/grants                  both halves of a link's grants built
POST   /api/folders/grants                  grant one path to one handle   built
DELETE /api/folders/grants/{id}             revoke a grant                 built
DELETE /api/folders/links/{id}              revoke the link, and its reads built
```

The grant and revoke writes came forward out of order, deliberately: without a grant route the read
surface can only serve `public` files, and `public` is already published in the Card. The CV the whole
demo is about is `public-summary` — listed with a digest, contents only with a grant — so a read surface
without a grant route demonstrates nothing the index did not already say. Links are still made by
`POST /api/hub/connect`.

### Order

**A → B → C.** B is the demonstrable part. Building C first would produce endpoints that cannot answer
the only question that matters: may this caller read this byte?

## Invariants

Each of these is worth a test of its own.

1. **A hidden file and a file that never existed return the identical 404.** `private`, `shared` and
   `hidden` are never served, grant or no grant. Note that this is *stricter* than `folders.ADMITTED`,
   which admits `shared`: the read surface serves only what the owner already published a path for
   (`folders.SERVED`), so a read can never be the first time a byte of a file left the folder. A linked
   peer still sees a `shared` file in the manifest, which is the folder link's whole point; the manifest's
   `readable` flag is narrowed to match, so a client is never promised a byte the hub would refuse.
2. **Path traversal is refused at the HTTP edge**, where the encoding happens: `../`, `..%2f`, `%2e%2e`,
   unicode dot lookalikes, absolute paths, and a symlink pointing out of the folder.
3. **Served bytes match the manifest digest**, across the whole vault corpus. If they can drift, the
   handshake and the index are describing different files.
4. **No wildcard grant, ever.** A grant names one path and one handle. From ClaudeConnect's
   `authz.py:205`: one `*` raises on the first bad line, the file fails to load, and a failed load means
   nobody gets anything.
5. **Revoking a link kills outstanding secrets** on the next request, not on a cache expiry.
6. **A byte cap and streaming**, so one read cannot hold a worker. The `Range` policy is chosen
   explicitly rather than inherited.
7. **Rate limited per link**, as the admin surface already is per password.
8. **Reads are logged to `audit.py`** — who read what, when. An owner who grants a path can see it was
   used, which is what makes a grant a decision rather than a hole.

## What the built part still cannot do

Said here as well as in [LIMITS.md](LIMITS.md), because a plan page that only lists intentions is not a
map of what runs.

- **Both folders are on one disk.** `LocalFolderLink` is the only implementation. The handshake, the
  grants and the refusals are real and enforced; the network between two machines is not there.
  `GET /api/folders/status` says so in `honest`.
- **No route claims a handle, requests a link or accepts one.** Those three are what is left of slice C.
- **The owner's own key is minted by the operator** until the accept route exists.
- **A granted `shared` file is still not served.** Seen is not served; see invariant 1.

## Out of scope, deliberately

No encryption at rest, no folder sync, and nothing calling claudeconnect.io. The hub serves files it has
already decided the caller may read. Saying that plainly is better than implying a protection that was
not built.

## Tracking

The surface is [#116](https://github.com/reactbias/Adobee-Hive/issues/116), the remaining exchange work
is [#128](https://github.com/reactbias/Adobee-Hive/issues/128), and the cross-hub connect bug that shares
this code path is [#143](https://github.com/reactbias/Adobee-Hive/issues/143). What is not built is listed
in [LIMITS.md](LIMITS.md).
