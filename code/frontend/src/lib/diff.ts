import type { Change } from "../api";

/** One line of a change the owner signs: what it is, and its old and new value (either may be absent). */
export interface DiffLine {
  field: string;
  before?: string;
  after?: string;
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const text = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));
const value = (key: string, v: unknown) => (key === "price_chf" ? `CHF ${v}` : text(v));

/** Turns a card change into the few lines that actually differ: tags added or removed, a room's new price. */
export function readable(c: Change): DiffLine[] {
  const { field, before, after } = c;
  if (Array.isArray(before) && Array.isArray(after) && [...before, ...after].every((v) => typeof v === "string")) {
    return [
      ...before.filter((v) => !after.includes(v)).map((v) => ({ field, before: v as string })),
      ...after.filter((v) => !before.includes(v)).map((v) => ({ field, after: v as string })),
    ];
  }
  if (Array.isArray(before) && Array.isArray(after) && [...before, ...after].every((v) => isObj(v) && "id" in v)) {
    const old = new Map((before as Obj[]).map((u) => [u.id, u]));
    const kept = new Set((after as Obj[]).map((u) => u.id));
    const gone = (before as Obj[])
      .filter((u) => !kept.has(u.id))
      .map((u) => ({ field: text(u.name ?? u.id), before: text(u.name ?? u.id) }));
    return [
      ...gone,
      ...(after as Obj[]).flatMap((u) => {
        const was = old.get(u.id);
        const name = text(u.name ?? u.id);
        if (!was) return [{ field: name, after: text(u.name ?? u.id) }];
        return Object.keys(u)
          .filter((k) => text(u[k]) !== text(was[k]))
          .map((k) => ({ field: name, before: value(k, was[k]), after: value(k, u[k]) }));
      }),
    ];
  }
  if (isObj(before) && isObj(after)) {
    return [...new Set([...Object.keys(before), ...Object.keys(after)])]
      .filter((k) => text(before[k]) !== text(after[k]))
      .map((k) => ({
        field: k,
        ...(k in before ? { before: text(before[k]) } : {}),
        ...(k in after ? { after: text(after[k]) } : {}),
      }));
  }
  return [{ field, before: text(before), after: text(after) }];
}
