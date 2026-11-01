import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import {
  api,
  ApiError,
  OFFLINE,
  shownError,
  type JoinApplication,
  type ApplicationOutcome,
  type DirectoryHub,
  type Proof,
  type RegistrationPolicy,
} from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { canPickDirectory, fromFileList, pickDirectory, type PickedFolder } from "../lib/folderPick";
import {
  buildDraft,
  CONTACT_FLAGS,
  groupsOf,
  KINDS,
  slug,
  toEntity,
  VISIBILITIES,
  type CardDraft,
  type Listing,
  type Visibility,
} from "../lib/folderScan";
import { generateKeys, signApplication, type Keys } from "../lib/signing";

// Joining a hive without filling in a profile: point at a folder, and the Card is filled in from it. The folder is
// read in this page and never sent; only the Card the person approves is. Then only the gaps are asked for, the
// key is made here, and the exact document is shown before it is signed. The rules come from the hive itself
// (GET /api/hub/registration), so a hive with different rules is not misdescribed.
//
// A refusal is the hive's answer, a 200 with `state: "rejected"`, the checks that ran, a reason and a next step.
// It is shown as an answer. Only a failure to reach the hive at all is an error, and the form stays as it was.

const ID = /^[a-z0-9][a-z0-9-]{1,62}$/;
const PROOF_TYPES = ["dns-txt", "rel-me", "email"];

const empty = (): CardDraft => ({
  id: "",
  kind: "person",
  name: "",
  description: "",
  contact: [
    { channel: "email", value: "", flag: "public" },
    { channel: "phone", value: "", flag: "public" },
  ],
  offers: [],
  needs: [],
  features: [],
  units: [],
  structure: [],
});

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  const heading = useId();
  return (
    <section className="onboard-step stack" aria-labelledby={heading}>
      <h2>
        <span className="onboard-n" aria-hidden="true">
          {n}
        </span>{" "}
        <span id={heading}>{title}</span>
      </h2>
      {children}
    </section>
  );
}

/** What this hive asks, read from the hive. Without it, its generic defaults, and a line saying so. */
function Rules({ policy, failed }: { policy: RegistrationPolicy | null; failed: boolean }) {
  const { t } = useI18n();
  if (failed) return <p className="muted">{t("onboard.rules.unread")}</p>;
  if (!policy) return <p className="muted">{t("onboard.rules.loading")}</p>;
  return (
    <div className="stack tight">
      <p>
        <span className="status">{t(`finder.admission.${policy.policy}` as Key)}</span> {policy.means}
      </p>
      <p className="muted small">{t("onboard.rules.checks", { checks: policy.checks.join(" · ") })}</p>
      <p className="muted small">{t("onboard.rules.english")}</p>
    </div>
  );
}

/** Pick a folder, or type it all by hand. Then say, per part of it, what the Card may carry. */
function FolderStep({
  picked,
  visibility,
  onPicked,
  onVisibility,
  onRead,
  onByHand,
}: {
  picked: PickedFolder | null;
  visibility: Record<string, Visibility>;
  onPicked: (folder: PickedFolder) => void;
  onVisibility: (group: string, v: Visibility) => void;
  onRead: () => void;
  onByHand: () => void;
}) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [failed, setFailed] = useState(false);

  async function pick() {
    setFailed(false);
    if (!canPickDirectory()) return input.current?.click();
    try {
      onPicked(await pickDirectory());
    } catch (e) {
      // Closing the picker is a choice, not a failure.
      if ((e as Error).name !== "AbortError") setFailed(true);
    }
  }

  return (
    <div className="stack">
      <p className="onboard-local">{t("onboard.folder.local")}</p>
      <div className="row">
        <button type="button" onClick={pick}>
          {t("onboard.folder.pick")}
        </button>
        <button type="button" className="quiet" onClick={onByHand}>
          {t("onboard.folder.byHand")}
        </button>
        <input
          ref={input}
          type="file"
          hidden
          multiple
          {...{ webkitdirectory: "" }}
          onChange={async (e) => e.target.files?.length && onPicked(await fromFileList(e.target.files))}
        />
      </div>
      {failed && <p className="error">{t("onboard.folder.failed")}</p>}
      {picked && (
        <div className="stack tight">
          <p>{t("onboard.folder.picked", { folder: picked.folder, n: picked.files.length })}</p>
          <ul className="rows onboard-groups">
            {groupsOf(picked.files).map((g) => (
              <li key={g.path}>
                <span>
                  {g.path} <span className="muted small">{t("onboard.folder.files", { n: g.files })}</span>
                </span>
                <select
                  aria-label={g.path}
                  value={visibility[g.path] ?? "public-summary"}
                  onChange={(e) => onVisibility(g.path, e.target.value as Visibility)}
                >
                  {VISIBILITIES.map((v) => (
                    <option key={v} value={v}>
                      {t(`onboard.vis.${v}` as Key)}
                    </option>
                  ))}
                </select>
              </li>
            ))}
          </ul>
          <p className="muted small">{t("onboard.folder.hiddenNote")}</p>
          <button type="button" onClick={onRead}>
            {t("onboard.folder.read")}
          </button>
        </div>
      )}
    </div>
  );
}

/** Offers or needs: a title and a line each, added and removed by hand. */
function Listings({
  legend,
  items,
  onChange,
}: {
  legend: string;
  items: Listing[];
  onChange: (items: Listing[]) => void;
}) {
  const { t } = useI18n();
  const edit = (i: number, patch: Partial<Listing>) =>
    onChange(items.map((item, j) => (j === i ? { ...item, ...patch } : item)));
  return (
    <fieldset className="stack tight">
      <legend>{legend}</legend>
      {items.map((item, i) => (
        <div key={i} className="onboard-listing">
          <input
            aria-label={t("onboard.card.itemTitle")}
            value={item.title}
            onChange={(e) => edit(i, { title: e.target.value, id: slug(e.target.value).slice(0, 63) || "item" })}
          />
          <input
            aria-label={t("onboard.card.itemSummary")}
            value={item.summary}
            onChange={(e) => edit(i, { summary: e.target.value })}
          />
          <button type="button" className="quiet" onClick={() => onChange(items.filter((_, j) => j !== i))}>
            {t("onboard.card.remove")}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="quiet"
        onClick={() => onChange([...items, { id: "item", title: "", summary: "" }])}
      >
        {t("onboard.card.add")}
      </button>
    </fieldset>
  );
}

type IdState = "checking" | "free" | "taken" | "unchecked" | "invalid";

/** The id is checked against the hive it is meant for; another hive's index is not this backend's to ask. */
function useIdCheck(id: string, home: boolean): IdState {
  const [state, setState] = useState<IdState>("checking");
  useEffect(() => {
    if (!ID.test(id)) return setState("invalid");
    if (!home) return setState("unchecked");
    setState("checking");
    let live = true;
    const timer = setTimeout(() => {
      api
        .card(id)
        .then(() => live && setState("taken"))
        .catch((e) => live && setState(e instanceof ApiError && e.status === 404 ? "free" : "unchecked"));
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [id, home]);
  return state;
}

function CardForm({
  draft,
  onChange,
  idState,
}: {
  draft: CardDraft;
  onChange: (draft: CardDraft) => void;
  idState: IdState;
}) {
  const { t } = useI18n();
  const set = (patch: Partial<CardDraft>) => onChange({ ...draft, ...patch });
  const ids = { id: useId(), name: useId(), description: useId(), kind: useId() };
  const idLine: Record<IdState, Key> = {
    checking: "onboard.card.idChecking",
    free: "onboard.card.idFree",
    taken: "onboard.card.idTaken",
    unchecked: "onboard.card.idUnchecked",
    invalid: "onboard.card.idRule",
  };
  return (
    <div className="stack onboard-card">
      <div className="onboard-fields">
        <label htmlFor={ids.name}>{t("onboard.card.name")}</label>
        <input id={ids.name} value={draft.name} onChange={(e) => set({ name: e.target.value })} />
        <label htmlFor={ids.id}>{t("onboard.card.id")}</label>
        <div className="stack tight">
          <input
            id={ids.id}
            value={draft.id}
            spellCheck={false}
            onChange={(e) => set({ id: e.target.value.toLowerCase() })}
          />
          <span className={`small ${idState === "taken" || idState === "invalid" ? "onboard-warn" : "muted"}`}>
            {t(idLine[idState])}
          </span>
        </div>
        <label htmlFor={ids.kind}>{t("onboard.card.kind")}</label>
        <select id={ids.kind} value={draft.kind} onChange={(e) => set({ kind: e.target.value })}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`onboard.kind.${k}` as Key)}
            </option>
          ))}
        </select>
        <label htmlFor={ids.description}>{t("onboard.card.description")}</label>
        <textarea
          id={ids.description}
          rows={2}
          value={draft.description}
          onChange={(e) => set({ description: e.target.value })}
        />
      </div>

      <fieldset className="stack tight">
        <legend>{t("onboard.card.contact")}</legend>
        {draft.contact.map((c, i) => {
          const edit = (patch: Partial<typeof c>) =>
            set({ contact: draft.contact.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
          return (
            <div key={c.channel} className="onboard-contact">
              <span>{c.channel}</span>
              <input
                aria-label={t("onboard.card.contactValue", { channel: c.channel })}
                value={c.value}
                disabled={c.flag !== "public"}
                onChange={(e) => edit({ value: e.target.value })}
              />
              <select
                aria-label={t("onboard.card.contactFlag", { channel: c.channel })}
                value={c.flag}
                onChange={(e) => edit({ flag: e.target.value as typeof c.flag })}
              >
                {CONTACT_FLAGS.map((f) => (
                  <option key={f} value={f}>
                    {t(`onboard.flag.${f}` as Key)}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
        <p className="muted small">{t("onboard.card.contactHeld")}</p>
      </fieldset>

      <Listings legend={t("onboard.card.offers")} items={draft.offers} onChange={(offers) => set({ offers })} />
      <Listings legend={t("onboard.card.needs")} items={draft.needs} onChange={(needs) => set({ needs })} />

      {draft.structure.length > 0 && (
        <p className="muted small">
          {t("onboard.card.structure", {
            shown: draft.structure.filter((r) => r.visibility !== "private").length,
            kept: draft.structure.filter((r) => r.visibility === "private").length,
          })}
        </p>
      )}
    </div>
  );
}

function Proofs({ types, proofs, onChange }: { types: string[]; proofs: Proof[]; onChange: (p: Proof[]) => void }) {
  const { t } = useI18n();
  return (
    <fieldset className="stack tight">
      <legend>{t("onboard.proof.legend")}</legend>
      {proofs.map((p, i) => (
        <div key={i} className="onboard-listing">
          <select
            aria-label={t("onboard.proof.type")}
            value={p.type}
            onChange={(e) => onChange(proofs.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)))}
          >
            {types.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <input
            aria-label={t("onboard.proof.subject")}
            value={p.subject}
            onChange={(e) => onChange(proofs.map((x, j) => (j === i ? { ...x, subject: e.target.value } : x)))}
          />
          <button type="button" className="quiet" onClick={() => onChange(proofs.filter((_, j) => j !== i))}>
            {t("onboard.card.remove")}
          </button>
        </div>
      ))}
      {proofs.length > 0 && <p className="muted small">{t("onboard.proof.unverified")}</p>}
      <button type="button" className="quiet" onClick={() => onChange([...proofs, { type: types[0], subject: "" }])}>
        {t("onboard.proof.add")}
      </button>
    </fieldset>
  );
}

type Custody = "owner" | "hub";

/** Who holds the signing key, with what each choice costs. */
function KeyStep({
  custody,
  onCustody,
  keys,
  unsupported,
  id,
  saved,
  onSaved,
}: {
  custody: Custody;
  onCustody: (c: Custody) => void;
  keys: Keys | null;
  unsupported: boolean;
  id: string;
  saved: boolean;
  onSaved: (saved: boolean) => void;
}) {
  const { t } = useI18n();
  const name = useId();
  return (
    <div className="stack">
      <div className="onboard-custody" role="radiogroup" aria-label={t("onboard.key.title")}>
        <label>
          <input
            type="radio"
            name={name}
            checked={custody === "owner"}
            disabled={unsupported}
            onChange={() => onCustody("owner")}
          />
          {t("onboard.key.own")}
        </label>
        <label>
          <input type="radio" name={name} checked={custody === "hub"} onChange={() => onCustody("hub")} />
          {t("onboard.key.hub")}
        </label>
      </div>
      {unsupported && <p className="muted">{t("onboard.key.unsupported")}</p>}
      {custody === "hub" ? (
        <p className="onboard-cost">{t("onboard.key.hubCost")}</p>
      ) : (
        keys && (
          <div className="stack tight">
            <p>{t("onboard.key.ownWhy")}</p>
            <a
              className="btn ghost onboard-save"
              href={`data:application/x-pem-file;charset=utf-8,${encodeURIComponent(keys.pem)}`}
              download={`${id || "adobee"}.pem`}
            >
              {t("onboard.key.download")}
            </a>
            <p className="onboard-cost">{t("onboard.key.loss")}</p>
            <label className="row">
              <input type="checkbox" checked={saved} onChange={(e) => onSaved(e.target.checked)} />
              {t("onboard.key.saved")}
            </label>
          </div>
        )
      )}
    </div>
  );
}

function OutcomeView({
  outcome,
  onAgain,
  onUse,
  onAnother,
}: {
  outcome: ApplicationOutcome;
  onAgain: () => void;
  onUse: () => void;
  /** Back to the list of Hives: the only way on when this one did not admit the applicant. */
  onAnother: () => void;
}) {
  const { t } = useI18n();
  return (
    <section className={`onboard-outcome onboard-outcome--${outcome.state} stack`} aria-live="polite">
      <h2>{t(`onboard.outcome.${outcome.state}` as Key)}</h2>
      <p>{outcome.reason}</p>
      <p>
        <span className="eyebrow">{t("onboard.outcome.next")}</span> {outcome.next}
      </p>
      <ul className="rows tight">
        {outcome.checks.map((c) => (
          <li key={c.check}>
            <span className={`status ${c.ok ? "ok" : "no"}`}>
              {c.check} · {t(c.ok ? "admin.check.passed" : "admin.check.failed")}
            </span>
            <span className="muted small">{c.detail}</span>
          </li>
        ))}
      </ul>
      <p className="muted small">{t("onboard.outcome.english")}</p>
      <div className="row">
        {/* Only an admission may offer this Hive: saying "use it" after a refusal, or while a person is
            still reading the application, would not be true. Then another Hive is the way on, and it
            leads rather than hides in a quiet link. */}
        {outcome.state === "admitted" ? (
          <button onClick={onUse}>{t("onboard.outcome.use")}</button>
        ) : (
          <button onClick={onAnother}>{t("onboard.outcome.another")}</button>
        )}
        {outcome.state === "rejected" && (
          <button className="quiet" onClick={onAgain}>
            {t("onboard.outcome.again")}
          </button>
        )}
      </div>
    </section>
  );
}

/** Joining one hive: its rules, the folder or by hand, the Card, the key, the exact document, the answer. */
export default function Onboarding({
  hub,
  onBack,
  onUse,
}: {
  hub: DirectoryHub;
  onBack: () => void;
  onUse: (hub: string) => void;
}) {
  const { t } = useI18n();
  const applyAt = hub.apply_at || "/api/hub/register";
  const [policy, setPolicy] = useState<RegistrationPolicy | null>(null);
  const [policyFailed, setPolicyFailed] = useState(false);
  const [picked, setPicked] = useState<PickedFolder | null>(null);
  const [visibility, setVisibility] = useState<Record<string, Visibility>>({});
  const [draft, setDraft] = useState<CardDraft | null>(null);
  const [proofs, setProofs] = useState<Proof[]>([]);
  const [invite, setInvite] = useState("");
  const [custody, setCustody] = useState<Custody>("owner");
  const [keys, setKeys] = useState<Keys | null>(null);
  const [unsupported, setUnsupported] = useState(false);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState<ApplicationOutcome | null>(null);
  const idState = useIdCheck(draft?.id ?? "", hub.home);
  const inviteId = useId();

  useEffect(() => {
    let live = true;
    api
      .registrationPolicy(applyAt)
      .then((p) => live && setPolicy(p))
      .catch(() => live && setPolicyFailed(true));
    return () => {
      live = false;
    };
  }, [applyAt]);

  // One key per visit, made when there is a Card to sign. Where WebCrypto has no Ed25519, the hive holds it.
  useEffect(() => {
    if (!draft || keys || unsupported) return;
    let live = true;
    generateKeys().then((made) => {
      if (!live) return;
      if (made) setKeys(made);
      else {
        setUnsupported(true);
        setCustody("hub");
      }
    });
    return () => {
      live = false;
    };
  }, [draft, keys, unsupported]);

  const application = useMemo<JoinApplication | null>(
    () =>
      draft && {
        entity: toEntity(draft),
        public_key: custody === "owner" && keys ? keys.publicKey : "",
        proofs: proofs.filter((p) => p.subject.trim()).map((p) => ({ type: p.type, subject: p.subject.trim() })),
        invite: invite.trim(),
      },
    [draft, custody, keys, proofs, invite],
  );

  const ready =
    !!application &&
    !!draft?.name.trim() &&
    idState !== "invalid" &&
    idState !== "taken" &&
    (custody === "hub" || (!!keys && saved)) &&
    !busy;

  async function send() {
    if (!application) return;
    setBusy(true);
    setError("");
    try {
      const signed =
        custody === "owner" && keys
          ? { ...application, signature: await signApplication({ ...application }, keys.privateKey) }
          : application;
      setOutcome(await api.register(signed, applyAt));
    } catch (e) {
      setError(shownError((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  const title = t("onboard.title", { hub: hub.name || hub.hub });
  // Hoisted above every branch below: the way out of joining a Hive belongs to the panel, not to one
  // of its states. The outcome branch rendered its own section without it, so an applicant a Hive
  // refused could reach neither the Hive list nor any other Hive without reloading the page.
  const back = (
    <button type="button" className="quiet onboard-back" onClick={onBack}>
      {t("onboard.back")}
    </button>
  );
  if (outcome)
    return (
      <section className="onboard stack">
        {back}
        <h1>{title}</h1>
        <OutcomeView
          outcome={outcome}
          onAgain={() => setOutcome(null)}
          onUse={() => onUse(hub.hub)}
          onAnother={onBack}
        />
      </section>
    );

  const types = policy?.proof_types.length ? policy.proof_types : PROOF_TYPES;
  return (
    <section className="onboard stack">
      {back}
      <h1>{title}</h1>
      <p>{t("onboard.lead")}</p>

      <Step n={1} title={t("onboard.rules.title")}>
        <Rules policy={policy} failed={policyFailed} />
      </Step>

      <Step n={2} title={t("onboard.folder.title")}>
        <FolderStep
          picked={picked}
          visibility={visibility}
          onPicked={(folder) => {
            setPicked(folder);
            setVisibility({});
          }}
          onVisibility={(group, v) => setVisibility((all) => ({ ...all, [group]: v }))}
          onRead={async () => picked && setDraft(await buildDraft(picked.folder, picked.files, visibility))}
          onByHand={() => {
            setPicked(null);
            setDraft(empty());
          }}
        />
      </Step>

      {draft && (
        <>
          <Step n={3} title={t("onboard.card.title")}>
            <CardForm draft={draft} onChange={setDraft} idState={idState} />
            <Proofs types={types} proofs={proofs} onChange={setProofs} />
            {policy?.policy === "invite" && (
              <div className="onboard-fields">
                <label htmlFor={inviteId}>{t("onboard.invite")}</label>
                <input id={inviteId} value={invite} onChange={(e) => setInvite(e.target.value)} />
              </div>
            )}
          </Step>

          <Step n={4} title={t("onboard.key.title")}>
            <KeyStep
              custody={custody}
              onCustody={setCustody}
              keys={keys}
              unsupported={unsupported}
              id={draft.id}
              saved={saved}
              onSaved={setSaved}
            />
          </Step>

          <Step n={5} title={t("onboard.review.title")}>
            <p className="muted small">{t("onboard.review.lead")}</p>
            <pre className="onboard-json">{JSON.stringify(application, null, 2)}</pre>
            {policy?.policy === "closed" && <p className="onboard-warn">{t("onboard.rules.closedNote")}</p>}
            <button onClick={send} disabled={!ready || policy?.policy === "closed"}>
              {busy ? t("onboard.sending") : t(custody === "owner" ? "onboard.sign" : "onboard.apply")}
            </button>
            {error && <p className="error">{error === OFFLINE ? t("error.offline") : error}</p>}
          </Step>
        </>
      )}
    </section>
  );
}
