import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, type HiringInterview, type HiringMatch, type HiringShortlist } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import { SAMPLES } from "../lib/hiringSamples";
import HiringPanel from "./HiringPanel";

const job = (over: Partial<HiringShortlist["job"]> = {}): HiringShortlist["job"] => ({
  title: "Engineer",
  requirements: [
    { label: "Python", options: ["Python"], kind: "must", related: [] },
    {
      label: "Cloud (AWS, Azure or GCP)",
      options: ["AWS", "Azure", "GCP", "cloud"],
      kind: "must",
      related: ["kubernetes"],
    },
    { label: "Mentoring", options: ["Mentoring"], kind: "nice", related: [] },
  ],
  min_years: 5,
  location: null,
  languages: ["en"],
  remote_ok: false,
  parsed_by: "rules",
  ...over,
});

const match = (id: string, name: string, score: number): HiringMatch => ({
  id,
  name,
  headline: "",
  description: "",
  score,
  musts_met: 2,
  musts_total: 2,
  evidence: [
    {
      requirement: "Python",
      kind: "must",
      strength: 1,
      how: "literal",
      covered: true,
      quote: "Python services at Acme",
    },
  ],
  gaps: ["Mentoring"],
  years: { stated: 9, note: "states 9 years; 5+ asked" },
  not_stated: [],
  signature_valid: true,
});

const shortlist = (...people: HiringMatch[]): HiringShortlist => ({
  job: job(),
  matches: people,
  excluded: [{ id: "x", name: "Xavier", why_not: ["nothing on the card speaks to any requirement"], score: 0 }],
  considered: people.length + 1,
  ranking_policy: "x",
});

const talked = (consent: "granted" | "awaiting_consent"): HiringInterview => ({
  job: job(),
  recruiter: "hiring-agent",
  summary: "",
  next_step: "",
  ranking_policy: "",
  excluded: [],
  ranking: [
    {
      id: "elena",
      name: "Elena",
      rank: 1,
      stage1_score: 70,
      score: 90,
      verdict: "strong",
      status: "interviewed",
      musts_met: 2,
      musts_total: 2,
      strengths: ["Python"],
      gaps: [],
      years: { stated: 10, note: "CV shows 10 years; 5+ asked" },
      consent: { state: "granted", why: "", granted: ["cv.json"] },
      read: ["about.md", "cv.json"],
      transcript: [
        {
          question: "What is your hands-on experience with Python?",
          about: "Python",
          answer: {
            text: "Yes",
            support: "direct",
            strength: 1,
            quotes: [{ text: "Developed microservices in Python", source: "cv.json" }],
          },
        },
        {
          question: "What are your rates?",
          about: "rate",
          answer: { text: "My shared files do not say my rates.", support: "none", strength: 0, quotes: [] },
        },
      ],
    },
    {
      id: "lena",
      name: "Lena",
      rank: 2,
      stage1_score: 60,
      score: consent === "granted" ? 80 : 60,
      verdict: consent === "granted" ? "promising" : "not interviewed",
      status: consent === "granted" ? "interviewed" : "awaiting_consent",
      musts_met: 1,
      musts_total: 2,
      strengths: [],
      gaps: ["Python"],
      years: { stated: null, note: "" },
      consent: { state: consent, why: "", granted: consent === "granted" ? ["cv.json"] : undefined },
      ...(consent === "granted" ? { read: ["cv.json"], transcript: [] } : {}),
    },
  ],
});

function draw() {
  render(
    <I18nProvider>
      <HiringPanel />
    </I18nProvider>,
  );
}

describe("hiring", () => {
  beforeEach(() => {
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.clear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("starts on a sample posting and shows the people who fit it, with what it understood", async () => {
    const find = vi.spyOn(api, "hiringShortlist").mockResolvedValue(shortlist(match("elena", "Elena", 88)));
    draw();
    expect(screen.getByLabelText(en["hire.posting"])).toHaveValue(SAMPLES[0].text);
    await act(() => vi.advanceTimersByTimeAsync(600));
    expect(find).toHaveBeenCalledWith(SAMPLES[0].text);
    expect(await screen.findByText("Elena")).toBeInTheDocument();
    expect(screen.getByText(en["hire.musts"].replace("{met}", "2").replace("{total}", "2"))).toBeInTheDocument();
    expect(screen.getByText(en["hire.gaps"].replace("{gaps}", "Mentoring"))).toBeInTheDocument();
    expect(screen.getByText(/Xavier/)).toBeInTheDocument();
    // One chip per requirement, and the run of alternatives is one of them.
    expect(screen.getByText(/Cloud \(AWS, Azure or GCP\)/)).toBeInTheDocument();
    expect(screen.getByText(en["hire.facts"].replace("{facts}", "5+, en"))).toBeInTheDocument();
  });

  it("changes the people when the posting changes, and does not ask on every keystroke", async () => {
    const find = vi
      .spyOn(api, "hiringShortlist")
      .mockResolvedValueOnce(shortlist(match("elena", "Elena", 88)))
      .mockResolvedValueOnce(shortlist(match("hannah", "Hannah", 91)));
    draw();
    await act(() => vi.advanceTimersByTimeAsync(600));
    expect(await screen.findByText("Elena")).toBeInTheDocument();

    const box = screen.getByLabelText(en["hire.posting"]);
    fireEvent.change(box, { target: { value: "Marketing" } });
    fireEvent.change(box, { target: { value: "Marketing Manager" } });
    await act(() => vi.advanceTimersByTimeAsync(600));
    expect(find).toHaveBeenCalledTimes(2);
    expect(find).toHaveBeenLastCalledWith("Marketing Manager");
    expect(await screen.findByText("Hannah")).toBeInTheDocument();
    expect(screen.queryByText("Elena")).not.toBeInTheDocument();
  });

  it("takes a sample from the list", async () => {
    vi.spyOn(api, "hiringShortlist").mockResolvedValue(shortlist());
    draw();
    fireEvent.change(screen.getByLabelText(en["hire.sample"]), { target: { value: SAMPLES[1].id } });
    expect(screen.getByLabelText(en["hire.posting"])).toHaveValue(SAMPLES[1].text);
  });

  it("starts the interviews only when asked, then lets the agents talk one exchange at a time", async () => {
    vi.spyOn(api, "hiringShortlist").mockResolvedValue(shortlist(match("elena", "Elena", 88)));
    const interview = vi.spyOn(api, "hiringInterview").mockResolvedValue(talked("granted"));
    draw();
    await act(() => vi.advanceTimersByTimeAsync(600));
    await screen.findByText("Elena");
    expect(interview).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: en["hire.start"] }));
    await vi.waitFor(() => expect(interview).toHaveBeenCalledWith(SAMPLES[0].text));
    const log = await screen.findByRole("log");
    expect(screen.getByText(en["hire.opens"].replace("{files}", "about.md, cv.json"))).toBeInTheDocument();
    expect(within(log).queryByText(/hands-on experience/)).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(within(log).getByText(/hands-on experience with Python/)).toBeInTheDocument();
    expect(within(log).getByText(/Developed microservices in Python/)).toBeInTheDocument();
    expect(within(log).queryByText(/What are your rates/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: en["hire.skip"] }));
    expect(within(log).getByText(/What are your rates/)).toBeInTheDocument();
    expect(within(log).getByText(/do not say my rates/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: en["hire.step4"] })).toBeInTheDocument();
  });

  it("says when the posting has changed since the interview", async () => {
    vi.spyOn(api, "hiringShortlist").mockResolvedValue(shortlist(match("elena", "Elena", 88)));
    vi.spyOn(api, "hiringInterview").mockResolvedValue(talked("granted"));
    draw();
    await act(() => vi.advanceTimersByTimeAsync(600));
    await screen.findByText("Elena");
    fireEvent.click(screen.getByRole("button", { name: en["hire.start"] }));
    await screen.findByRole("log");
    fireEvent.change(screen.getByLabelText(en["hire.posting"]), { target: { value: "Something else entirely" } });
    expect(screen.getByText(en["hire.stale"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["hire.again"] })).toBeInTheDocument();
  });

  it("lets a person's yes be given for them, then interviews again", async () => {
    vi.spyOn(api, "hiringShortlist").mockResolvedValue(shortlist(match("elena", "Elena", 88)));
    const interview = vi
      .spyOn(api, "hiringInterview")
      .mockResolvedValueOnce(talked("awaiting_consent"))
      .mockResolvedValueOnce(talked("granted"));
    const yes = vi.spyOn(api, "hiringScreening").mockResolvedValue({ card_id: "lena", screening: "yes" });
    draw();
    await act(() => vi.advanceTimersByTimeAsync(600));
    await screen.findByText("Elena");
    fireEvent.click(screen.getByRole("button", { name: en["hire.start"] }));
    expect(await screen.findByText(en["hire.consent.awaiting_consent"])).toBeInTheDocument();
    expect(screen.getByText(en["hire.sayYesHint"])).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: en["hire.sayYes"].replace("{name}", "Lena") }));
    await vi.waitFor(() => expect(yes).toHaveBeenCalledWith("lena", "yes"));
    await vi.waitFor(() => expect(interview).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(screen.queryByText(en["hire.consent.awaiting_consent"])).not.toBeInTheDocument());
  });

  it("asks for the owner token when the hub wants one, and uses it", async () => {
    vi.spyOn(api, "hiringShortlist").mockResolvedValue(shortlist(match("elena", "Elena", 88)));
    vi.spyOn(api, "hiringInterview")
      .mockResolvedValueOnce(talked("awaiting_consent"))
      .mockResolvedValueOnce(talked("granted"));
    const yes = vi
      .spyOn(api, "hiringScreening")
      .mockRejectedValueOnce(new ApiError("Missing or wrong X-Owner-Token.", 403))
      .mockResolvedValueOnce({ card_id: "lena", screening: "yes" });
    draw();
    await act(() => vi.advanceTimersByTimeAsync(600));
    await screen.findByText("Elena");
    fireEvent.click(screen.getByRole("button", { name: en["hire.start"] }));
    fireEvent.click(await screen.findByRole("button", { name: en["hire.sayYes"].replace("{name}", "Lena") }));

    expect(await screen.findByText(en["hire.needsToken"])).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(en["hire.token"]), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByRole("button", { name: en["hire.tokenSave"] }));
    await vi.waitFor(() => expect(yes).toHaveBeenCalledTimes(2));
    expect(sessionStorage.getItem("adobee-owner-token")).toBe("s3cret");
  });

  it("says so, in words, when the hive can not be reached", async () => {
    vi.spyOn(api, "hiringShortlist").mockRejectedValue(new Error("error.offline"));
    draw();
    await act(() => vi.advanceTimersByTimeAsync(600));
    expect(await screen.findByRole("alert")).toHaveTextContent(en["error.offline"]);
  });

  it("does not offer to interview when nobody fits", async () => {
    vi.spyOn(api, "hiringShortlist").mockResolvedValue(shortlist());
    draw();
    await act(() => vi.advanceTimersByTimeAsync(600));
    expect(await screen.findByText(en["hire.noMatch"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["hire.start"] })).toBeDisabled();
  });
});
