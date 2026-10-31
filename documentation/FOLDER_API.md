# Folder API — opening a link, and reading one file out of it

The public index gets an agent to a candidate. It does not get it the candidate's folder. This page
is the door between the two: how a client opens a folder link, gets the manifest that link opened,
is granted one path, and reads those bytes.

Every command below was run against a hub started from this branch, and every JSON body on this page
is a real response with nothing added and nothing tidied — **except the two link secrets**, which
are replaced with `EXAMPLE-not-a-real-secret-…` and then carried in shell variables. The real ones
were 32 urlsafe bytes and died with that hub's database; a page in a public repo that prints
something shaped like a live credential, or a `curl` with a literal `Authorization` header, fails
the repo's own secret scan — and rightly, which is why the commands below read the secret from a
variable the way you would anyway.

**Contents**

- [The four things to know first](#the-four-things-to-know-first)
- [Run it](#run-it)
- [The walkthrough: a CV out of a stranger's folder](#the-walkthrough-a-cv-out-of-a-strangers-folder)
- [The endpoints](#the-endpoints)
- [Every refusal, and why they all look the same](#every-refusal-and-why-they-all-look-the-same)
- [What this does not do](#what-this-does-not-do)

---

## The four things to know first

1. **The credential is the link, not an account.** This hub has no user accounts. When a folder link
   is established, one party is handed 32 random bytes; presenting them as
   `Authorization: Bearer <secret>` is how a read says who it is. The secret is returned **exactly
   once**, stored only as its SHA-256, and never logged. Revoking the link kills it on the next
   request, because the link's state is re-read every time — there is no session to expire.

2. **The read endpoints take no handle.** `GET /api/folders/manifest` and
   `GET /api/folders/file` derive both the owner and the viewer from the bearer. There is no
   `?viewer=` and no `?owner=`, so a caller cannot ask about a folder it holds no link to and there
   is nothing to enumerate. Adding a query parameter changes nothing; `test_folder_api.py` pins that.

3. **A link opens the manifest. A grant opens the bytes.** Those are two decisions and the hub asks
   them separately. `public` is the one exception — it is already published, so a grant for it would
   be theatre. Everything else needs a grant that names **one path and one handle**. There is no
   wildcard, no pattern, and no whole-folder grant on this surface.

4. **Every refusal is the same refusal.** A hidden file, a private file, an ungranted file, a file
   that never existed and a path that tries to climb out of the folder all answer `404` with the
   same sentence. Distinguishable noes let a caller map a folder it cannot read.

---

## Run it

```bash
cd code/backend
HIVE_HUB_ID=docs ADMISSION_POLICY=open SEED_ON_EMPTY=false \
  ADMIN_TOKEN=an-operator-secret DUCKDB_PATH=/tmp/folders.duckdb \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8481
```

Then put one folder in its index, through the real signup endpoint:

```bash
.venv/bin/python tools/seed_vaults.py --hub http://127.0.0.1:8481 --only anouk-pfister
```

```
  ✓ anouk-pfister    admitted  8 files  admitted automatically: this hub admits anything that passes its check
```

`anouk-pfister` is one of the 61 fictional folders in [`testdata/`](../testdata/README.md). Her
`visibility.md` says one line — `arbeitsproben.pdf: public` — so everything else in the folder,
`cv.pdf` included, falls to the default `public-summary`: **listed with a digest, contents only with
a grant.** That is the interesting case and it is why this walkthrough uses her.

What the hub says about its own folder layer, with no credential at all:

```bash
curl -s http://127.0.0.1:8481/api/folders/status
```

```json
{
  "folder_link": "local",
  "requested": "local",
  "why": "local folders",
  "served_visibilities": ["public", "public-summary"],
  "max_read_bytes": 26214400,
  "reads_per_link_hour": 600,
  "ranges": "not supported; a read is the whole file or a 413",
  "honest": "On the local folder link the handshake and the grants are real and enforced, and both folders are on one disk. Nothing here crosses a machine."
}
```

`honest` is there to be printed. A screen that implied two machines would be the page that is wrong.

---

## The walkthrough: a CV out of a stranger's folder

### 1. Connect, and get the key in the same answer

`POST /api/hub/connect` already did the handshake before this surface existed. It now also hands the
**requester** the secret for its side of the link, so one call is enough to go from "found her in the
index" to "holding the folder".

```bash
curl -s -X POST http://127.0.0.1:8481/api/hub/connect \
  -H 'content-type: application/json' \
  -d '{"requester":"Mara Keller","entity_id":"anouk-pfister"}'
```

The whole introduction row comes back; these are the three fields this page is about:

```json
{
  "folder_link": "fl-94d0cde9a3e5",
  "folder": { "owner": "anouk-pfister", "viewer": "mara-keller", "linked": true, "files": [], "withheld": 0 },
  "folder_key": {
    "id": "fk-6b2f0c0a1d4e",
    "link": "fl-94d0cde9a3e5",
    "handle": "mara-keller",
    "peer": "anouk-pfister",
    "secret": "EXAMPLE-not-a-real-secret-viewer",
    "scheme": "Bearer"
  }
}
```

`files` is abbreviated above only to keep this page readable — the real answer carries the manifest
in full, the same one step 2 fetches. **`secret` is in this response and in no other.** A `confirm`
card's link is still `requested` at this point, so `folder_key` is `null` until its owner says yes.

> `folder.readable` in *this* answer is the folder link's own view (`folders.can_read`). The
> `/api/folders/manifest` route narrows it to what it will actually serve — see step 2's note.

Keep three things out of that answer; every command below uses them:

```bash
HUB=http://127.0.0.1:8481
LINK=fl-94d0cde9a3e5                              # .folder_link
VIEWER=EXAMPLE-not-a-real-secret-viewer           # .folder_key.secret
```

### 2. The manifest: what this link may see

```bash
curl -s "$HUB/api/folders/manifest" -H "Authorization: Bearer $VIEWER"
```

```json
{
  "owner": "anouk-pfister",
  "viewer": "mara-keller",
  "linked": true,
  "files": [
    { "path": "about.md", "bytes": 174, "media_type": "text/markdown", "digest": "sha256:efc7a857ddb7",
      "visibility": "public-summary", "ref": "anouk-pfister/about.md", "readable": false },
    { "path": "arbeitsproben.pdf", "bytes": 993, "media_type": "application/pdf", "digest": "sha256:7134d1d2c4ef",
      "visibility": "public", "ref": "anouk-pfister/arbeitsproben.pdf", "readable": true },
    { "path": "contact.md", "bytes": 68, "media_type": "text/markdown", "digest": "sha256:9737a0468ab8",
      "visibility": "public-summary", "ref": "anouk-pfister/contact.md", "readable": false },
    { "path": "cv.pdf", "bytes": 1173, "media_type": "application/pdf", "digest": "sha256:40f8983cdd34",
      "visibility": "public-summary", "ref": "anouk-pfister/cv.pdf", "readable": false }
  ],
  "withheld": 0,
  "link": "fl-94d0cde9a3e5"
}
```

Four of the eight rows are shown; the rest are the same shape. Two things to read off it:

- `readable` is **what the file route will actually hand over**, not merely what the access rules
  permit. A linked peer *sees* a `shared` file here — that is the folder link's whole point, since
  the Card never admitted it existed — but this hub serves bytes only for `public` and
  `public-summary` (`folders.SERVED`), so a `shared` row reads `readable: false` even with a grant.
  One definition, so a client is never promised a byte it would then be refused.
- `withheld` is a **number**. It is `0` here because Anouk marks nothing `private` or `hidden`; in
  `jonas-brun`'s folder, where `projekte/` is private, it is the count of those files and never
  their names. Not in the manifest, not in an error, not under any flag.

### 3. `cv.pdf`, before anyone granted it

```bash
curl -s -i "$HUB/api/folders/file?path=cv.pdf" -H "Authorization: Bearer $VIEWER"
```

```
HTTP/1.1 404 Not Found
```
```json
{ "detail": "No such file here, or none this link may read." }
```

Listed, digested, and not readable. The manifest said as much.

### 4. The owner's own key

A grant is the owner's to give, so the owner needs a credential of its own for this link. The door
an owner's agent walks through itself is the accept route; until that exists, the hub's operator
mints one. **This is the hub's token and it does not prove per-owner identity** — see
[What this does not do](#what-this-does-not-do).

```bash
OPERATOR=an-operator-secret   # the hub's ADMIN_TOKEN, from the command that started it

curl -s -X POST "$HUB/api/folders/keys" -H 'content-type: application/json' \
  -H "X-Admin-Token: $OPERATOR" -d "{\"link\":\"$LINK\",\"handle\":\"anouk-pfister\"}"
```

```json
{
  "id": "fk-8999b5b4a2fd",
  "link": "fl-94d0cde9a3e5",
  "handle": "anouk-pfister",
  "peer": "mara-keller",
  "secret": "EXAMPLE-not-a-real-secret-owner",
  "scheme": "Bearer"
}
```

### 5. One path, to one handle

The body carries **only a path**. Whose folder it is and who it is being opened to are both already
decided by the bearer, which is what makes this a per-owner write on a hub with no owner accounts.

```bash
OWNER=EXAMPLE-not-a-real-secret-owner             # .secret, from the answer above

curl -s -X POST "$HUB/api/folders/grants" -H 'content-type: application/json' \
  -H "Authorization: Bearer $OWNER" -d '{"path":"cv.pdf"}'
```

```json
{
  "id": "fg-9afb86356cb1",
  "owner": "anouk-pfister",
  "path": "cv.pdf",
  "ref": "anouk-pfister/cv.pdf",
  "to": "mara-keller",
  "link": "fl-94d0cde9a3e5"
}
```

### 6. The bytes

```bash
curl -s -D - -o cv.pdf "$HUB/api/folders/file?path=cv.pdf" -H "Authorization: Bearer $VIEWER"
```

```
HTTP/1.1 200 OK
content-length: 1173
etag: "sha256:40f8983cdd34"
accept-ranges: none
cache-control: private, no-store
x-folder-link: fl-94d0cde9a3e5
content-type: application/pdf
```

```bash
wc -c < cv.pdf && sha256sum cv.pdf | cut -c1-12
```
```
1173
40f8983cdd34
```

**The digest is the one the manifest published**, so the index and the handshake are describing the
same file. `test_folder_api.py` asserts that over the whole 61-folder corpus and not only here.
The file is streamed in 64 KiB pieces, so a big PDF is never a big heap.

### 7. Taking it back

Either party may withdraw the link, and neither needs the other's permission to stop:

```bash
curl -s -X DELETE "$HUB/api/folders/links/$LINK" -H "Authorization: Bearer $OWNER"
```

```json
{
  "id": "fl-94d0cde9a3e5",
  "state": "revoked",
  "from_handle": "mara-keller",
  "to_handle": "anouk-pfister",
  "accepted_at": "2026-10-31T22:46:39.782756",
  "accepted_by": "anouk-pfister",
  "revoked": true,
  "secrets_retired": 2
}
```

The very next read with either secret is `401`, not a cached `200`. To take back one path instead of
the whole relationship, `DELETE /api/folders/grants/{grant_id}`.

---

## The endpoints

| Method | Path | Credential | What it does |
| --- | --- | --- | --- |
| `GET` | `/api/folders/status` | none | Which link is in use, what was asked for, why they differ, what a read costs, and the honest line about one disk. Names no server path |
| `GET` | `/api/folders/manifest` | `Bearer <link secret>` | The peer's folder as this link may see it, with `withheld` as a count |
| `GET` | `/api/folders/file` | `Bearer <link secret>` | The bytes of one file, streamed, if a grant names that path. Rate-limited per link |
| `GET` | `/api/folders/grants` | `Bearer <link secret>` | Both halves of this link's grants, `given` and `received`, kept apart |
| `POST` | `/api/folders/grants` | `Bearer <link secret>` | Open one path of the caller's **own** folder to the peer on this link |
| `DELETE` | `/api/folders/grants/{id}` | `Bearer <link secret>` | Take one grant back. Only the owner who gave it may |
| `DELETE` | `/api/folders/links/{id}` | `Bearer <link secret>` | Withdraw the link, and with it every secret and read it allowed |
| `POST` | `/api/folders/keys` | `X-Admin-Token`, fails closed | Mint a link secret for one party, returned once. The operator's door, not the owner's |
| `POST` | `/api/hub/connect` | rate limit | Also returns `folder_key` for the requester it names, once. And takes `card` + `target_hub` for an entity on a **peer**, verified against that hub's pinned key (#143) |

`GET /api/folders/file` sets `ETag` to the manifest's digest, `Accept-Ranges: none`,
`Cache-Control: private, no-store` and `X-Folder-Link`. A file over `FOLDER_READ_MAX_BYTES`
(25 MiB) is `413`; there is no partial answer, by decision rather than by omission.

Every served read is one `folder.read` row in the admin ledger
(`GET /api/admin/audit?action=folder.read`), carrying the path, the time, the key id and — uniquely
in that ledger — the **handle** that read it. Every other row in it reads `admin`, because the hub's
own credentials name no person; a link secret does name a handle, which is why an owner who grants a
path can afterwards see it was used.

---

## Every refusal, and why they all look the same

```bash
for p in honorar-2026.csv cv.pdf.bak '..%2fmara-keller%2fstolen.md'; do
  curl -s "$HUB/api/folders/file?path=$p" -H "Authorization: Bearer $VIEWER"; echo
done
```

```
{"detail":"No such file here, or none this link may read."}
{"detail":"No such file here, or none this link may read."}
{"detail":"No such file here, or none this link may read."}
```

One is a real file this link has no grant on. One never existed. One is a traversal attempt. They
are the same status and the same sentence, and a `private` or `hidden` file joins them. The tests
pin this from the HTTP edge, where the percent-decoding happens, over `../`, `..%2f`, `%2e%2e`,
unicode dot lookalikes, absolute paths, a NUL byte, and a symlink pointing out of the folder.

| What you sent | What you get |
| --- | --- |
| no bearer, a wrong bearer, a revoked key, or a revoked link | `401` with `WWW-Authenticate: Bearer`, one sentence for all four |
| a path that is hidden, private, ungranted, absent, or a traversal | `404` with one sentence for all five |
| a grant naming a pattern, the whole folder, or a path the owner never admitted | `400`, and the same words for a hidden path as for a missing one |
| more reads than the link's hourly budget | `429` with `Retry-After` |
| a file over the cap | `413` saying both numbers |

---

## What this does not do

Said plainly, because a false claim in front of a jury costs more than a missing feature.

- **Both folders are on one disk.** `LocalFolderLink` is the only implementation that runs today. The
  handshake, the grants and the refusals are real and enforced; the network between two machines is
  not there. `GET /api/folders/status` says so in `honest`, and
  [LIMITS.md](LIMITS.md#the-folder-link) says it again.
- **`POST /api/folders/keys` is the hub's token, not the owner's.** It mints a secret *on behalf of* a
  handle. On a hub with one shared operator credential that is what it is, and it is not proof of
  that handle's own identity. The doors that genuinely speak for a party are `POST /api/hub/connect`,
  for the requester it names, and the accept route, which is not built yet.
- **There is no route to claim a handle, request a link or accept one.** Links are made by
  `POST /api/hub/connect`. Issue [#116](https://github.com/reactbias/Adobee-Hive/issues/116) has the
  shape of the rest.
- **A granted `shared` file still is not served.** Seen is not served; see `folders.SERVED`.
- **No encryption at rest, no folder sync, nothing calling claudeconnect.io.** The hub serves files it
  has already decided the caller may read. Saying that beats implying a protection nobody built.
