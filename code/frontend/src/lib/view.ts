// Which view the address asks for, and how to keep the address honest about it.
//
// One rule, for `?admin` and `?hub=` alike:
//
//   **The address decides the view, and a view never shares the address with a parameter belonging to another.**
//
// Both parameters are sticky, because the page navigates by hash (`#find`, `#offer`, `#network`) and a hash
// change does not touch the query. So `?admin` survived every click and you ended up in the hub's own panel on a
// screen anchor: `http://host/?admin#find`, a URL that claims two views at once and renders a hybrid. `?hub=`
// had the same fault on the way out of the finder, which is what "change hive does nothing" was.
//
// The fix is this module plus two listeners in App: the view is read from the address rather than frozen at
// mount, and any in-app navigation out of the hub's panel takes `?admin` out of the address with it. Nothing is
// taken away from either entry point — `?admin` still opens the panel, `?hub=<id>` still skips the finder for the
// pitch runbook — they just stop outliving the view they chose.

/** The two things the address can ask for. There is no third, and never both at once. */
export type View = "admin" | "app";

const params = (search: string) => new URLSearchParams(search);

/** Which view an address asks for. `?admin` means the hub's own panel; everything else is the app. */
export function viewIn(search: string): View {
  return params(search).has("admin") ? "admin" : "app";
}

/**
 * The hub an address picks, or "" for none.
 *
 * `?hub=<id>` skips the finder, which is what the pitch runbook opens with. `?hub` on its own means whatever
 * this backend serves, so a driver can type the short form.
 */
export function hubIn(search: string): string {
  const q = params(search);
  return q.has("hub") ? q.get("hub") || "local" : "";
}

/** The hub's base URL from `?hub_url=`, for a link that names a hub this app has never heard of. */
export function hubUrlIn(search: string): string {
  return params(search).get("hub_url") || "";
}

/**
 * An address with one query parameter removed, and optionally the hash too.
 *
 * The hash goes when the parameter being dropped decided the view: a hash is an anchor on a page, and keeping an
 * anchor from a page nobody is looking at is how `?admin#find` happened in the first place.
 */
export function without(url: URL, name: string, keepHash = true): string {
  // Edited as text, not through URLSearchParams: its toString writes a valueless `?demo` back as `?demo=`, and
  // a parameter quietly respelled on the way past is the same class of weird link as one that would not leave.
  const query = url.search
    .replace(/^\?/, "")
    .split("&")
    .filter((pair) => pair && decodeURIComponent(pair.split("=")[0]) !== name)
    .join("&");
  return `${url.pathname}${query ? `?${query}` : ""}${keepHash ? url.hash : ""}`;
}

/**
 * True when an address asks for two views at once, which no reachable URL should.
 *
 * A hash is an anchor on the app's one page. The hub's own panel has no anchors, so `?admin` with any hash is a
 * hybrid, and it resolves to the panel with the stray anchor dropped.
 */
export function isHybrid(search: string, hash: string): boolean {
  return viewIn(search) === "admin" && hash.length > 1;
}
