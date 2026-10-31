import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, apiBase, setChosenHub } from "./api";
import App from "./App";
import { I18nProvider } from "./i18n";
import en from "./i18n/en";

// The app is one page: the traveller's group chat, with everything else behind the same door. api.ts is mocked.
//
// A first visit now lands on the instance finder, because you pick a Hive before you use one. These tests
// describe the app *after* a hub is chosen, so they set the choice the finder would have made; the finder's own
// behaviour is at the bottom of this file and in panels/InstanceFinder.test.tsx.

describe("the app", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.setItem("adobee-hub", "local");
    vi.spyOn(api, "health").mockResolvedValue({ llm: "mock", model: "", fast_model: "" } as never);
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "demand").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "activity").mockResolvedValue({ events: [], last: 0 });
    vi.spyOn(api, "discover").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "adminOverview").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "adminNeighbours").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "directory").mockRejectedValue(new Error("offline"));
  });

  it("opens on the traveller agent and links to no other page", async () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
    expect(await screen.findByText(en["nav.offline"])).toBeInTheDocument();
    const hrefs = screen.queryAllByRole("link").map((a) => a.getAttribute("href") ?? "");
    expect(hrefs.filter((h) => !h.startsWith("#") && !/^https?:/.test(h))).toEqual([]);
  });

  it("is two screens, one per person, switched in the header by hash", async () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const tabs = within(screen.getByRole("navigation", { name: en["nav.chapters"] }));
    const links = tabs.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["#travel", "#business"]);
    expect(links[0]).toHaveTextContent(en["chapter.travel"]);
    expect(links[1]).toHaveTextContent(en["chapter.business"]);
    expect(links[0]).toHaveAttribute("aria-current", "page");

    // The traveller's screen first; the business's is there but not on show.
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(en["find.title"]);
    expect(screen.queryByRole("heading", { name: en["chapter.business.title"].replace(/\*/g, "") })).toBeNull();
    // Nothing is drawn until an endpoint returns it: no empty stage, no empty log.
    expect(screen.queryByRole("region", { name: en["card.stage"] })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: en["card.log"] })).not.toBeInTheDocument();

    const scrollTo = vi.fn();
    window.scrollTo = scrollTo as unknown as typeof window.scrollTo;
    window.location.hash = "#business";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(
      await screen.findByRole("heading", { name: en["chapter.business.title"].replace(/\*/g, "") }),
    ).toBeInTheDocument();
    // The screen opens at its top, not at the anchor the browser jumped to under the header.
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 0 }));
    expect(screen.queryByRole("heading", { name: en["find.title"] })).toBeNull();
    expect(links[1]).toHaveAttribute("aria-current", "page");
    window.location.hash = "";
  });

  it("opens the business screen on the card, with the city's demand one tab away", () => {
    window.history.replaceState(null, "", "/#business");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByRole("tab", { name: en["business.tab.owner"] })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: en["business.tab.demand"] })).toHaveAttribute("aria-selected", "false");
    window.history.replaceState(null, "", "/");
  });

  it("scrolls back to the top when the logo is clicked", async () => {
    const scrollTo = vi.fn();
    window.scrollTo = scrollTo as unknown as typeof window.scrollTo;
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    screen.getByRole("link", { name: "Adobee Hive" }).click();
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 0 }));
  });

  it("shows visitors no presenter tools", async () => {
    window.history.replaceState(null, "", "/");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.queryByText(en["agent.test.eyebrow"])).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["demand.simulate"] })).not.toBeInTheDocument();
  });

  it("gives presenters their tools with ?demo", async () => {
    window.history.replaceState(null, "", "/?demo");
    const { unmount } = render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByText(en["agent.test.eyebrow"])).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: en["reach.local"] })).toBeInTheDocument();
    unmount();

    window.history.replaceState(null, "", "/?demo#business");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    screen.getByRole("tab", { name: en["business.tab.demand"] }).click();
    expect(await screen.findByRole("button", { name: en["demand.simulate"] })).toBeInTheDocument();
    window.history.replaceState(null, "", "/");
  });

  it("keeps the hub network on its own screen, reached from the footer", async () => {
    window.history.replaceState(null, "", "/");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.queryByRole("heading", { name: en["network.title"] })).toBeNull();
    const link = screen.getByRole("link", { name: en["nav.network"] });
    expect(link).toHaveAttribute("href", "#network");

    window.location.hash = "#network";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findByRole("heading", { name: en["network.title"] })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: en["find.title"] })).toBeNull();
    window.location.hash = "";
  });

  it("offers an obvious way back to change hub", () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByRole("button", { name: en["finder.change"] })).toBeInTheDocument();
  });
});

// The first screen is the search, on the Hive this build was deployed against. Picking another Hive is one tap
// away (Change Hive), and `?hub=` still points the app at one for the pitch runbook; neither stands between a
// visitor and a booking run.
describe("the first screen", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.clear();
    window.history.replaceState(null, "", "/");
    vi.spyOn(api, "health").mockResolvedValue({ llm: "mock", model: "", fast_model: "" } as never);
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "demand").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [] });
  });

  it("is the search, with the question and the bar, when no hub has been chosen", async () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(en["find.title"]);
    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: en["finder.title"] })).toBeNull();
    // Nothing was chosen on the visitor's behalf: the home Hive is the default, not a remembered pick.
    expect(sessionStorage.getItem("adobee-hub")).toBeNull();
  });

  it("stays on the search across a reload, however many times", async () => {
    for (let n = 0; n < 3; n++) {
      const { unmount } = render(
        <I18nProvider>
          <App />
        </I18nProvider>,
      );
      expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: en["finder.title"] })).toBeNull();
      unmount();
    }
  });

  it("opens the finder from Change Hive, and is never blank when the directory is broken", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: undefined } as never);
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: en["finder.change"] }));
    expect(await screen.findByRole("heading", { name: en["finder.title"] })).toBeInTheDocument();
    expect(screen.getByText(en["finder.thisHub"])).toBeInTheDocument();
    expect(screen.queryByLabelText(en["agent.intent"])).toBeNull();
  });

  it("opens the application for a hive from Join, and goes back to the list from it", async () => {
    vi.mocked(api.directory).mockResolvedValue({
      hubs: [
        {
          hub: "local",
          url: "",
          home: true,
          blocked: false,
          name: "Hive Basel",
          description: "",
          admission: "open",
          accepting: true,
          entities: 1,
          apply_at: "/api/hub/register",
          error: null,
          error_stars: null,
          evidence: 0,
          verdict: "unproven",
          why: "",
        },
      ],
    });
    vi.spyOn(api, "registrationPolicy").mockRejectedValue(new Error("offline"));
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: en["finder.change"] }));
    await userEvent.click(await screen.findByRole("button", { name: en["finder.join"] }));
    expect(await screen.findByRole("heading", { name: "Join Hive Basel" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["onboard.back"] }));
    expect(await screen.findByRole("heading", { name: en["finder.title"] })).toBeInTheDocument();
  });

  it("is skipped once a hub has been chosen in this tab", () => {
    sessionStorage.setItem("adobee-hub", "local");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
  });

  it("is skipped by ?hub= in the address, which is what the pitch runbook uses", () => {
    window.history.replaceState(null, "", "/?hub=local");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
    window.history.replaceState(null, "", "/");
  });

  it("opens the hub's own panel with ?admin, and asks for the password", () => {
    window.history.replaceState(null, "", "/?admin");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(en["admin.password"])).toBeInTheDocument();
    expect(screen.queryByLabelText(en["agent.intent"])).toBeNull();
    window.history.replaceState(null, "", "/");
  });
});

// "Clicking change-hive brings you back to a page that is not the correct hive log." It did: ?hub= stayed in the
// address, so the finder re-applied it on the next read and bounced straight past itself.
describe("changing hive", () => {
  const offline = () => {
    vi.spyOn(api, "health").mockResolvedValue({ llm: "mock", model: "", fast_model: "" } as never);
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "demand").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "adminOverview").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "adminNeighbours").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "directory").mockResolvedValue({
      hubs: [
        {
          hub: "a",
          url: "",
          home: true,
          blocked: false,
          name: "Hive A",
          description: "",
          accepting: true,
          error: null,
          error_stars: null,
          evidence: 0,
          verdict: "unproven",
          why: "",
        },
        {
          hub: "b",
          // A peer the app can actually be pointed at: a hub with no address cannot be picked, by design.
          url: "http://10.0.0.2:8461",
          home: false,
          blocked: false,
          name: "Hive B",
          description: "",
          accepting: true,
          error: null,
          error_stars: null,
          evidence: 0,
          verdict: "unproven",
          why: "",
        },
      ],
    });
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.clear();
    window.history.replaceState(null, "", "/");
    offline();
  });

  it("goes back to the finder with nothing selected, and a reload is the search on the home Hive", async () => {
    sessionStorage.setItem("adobee-hub", "a");
    window.history.replaceState(null, "", "/?hub=a");
    const { unmount } = render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: en["finder.change"] }));
    expect(await screen.findByRole("heading", { name: en["finder.title"] })).toBeInTheDocument();
    expect(sessionStorage.getItem("adobee-hub")).toBeNull();
    expect(window.location.search).not.toContain("hub");

    // A reload at that point must not re-select the hub that was just dropped: it is the home Hive again.
    unmount();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
    expect(screen.queryByText(en["nav.onHub"].replace("{hub}", "a"))).toBeNull();
  });

  it("lets the next pick be a different hub, and remembers that one", async () => {
    sessionStorage.setItem("adobee-hub", "a");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: en["finder.change"] }));
    const rows = await screen.findAllByRole("listitem");
    await userEvent.click(within(rows[1]).getByRole("button", { name: en["finder.use"] }));

    expect(sessionStorage.getItem("adobee-hub")).toBe("b");
    expect(apiBase()).toBe("http://10.0.0.2:8461");
    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
  });

  it("says which backend the page is actually talking to", async () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: en["finder.change"] }));
    expect(await screen.findByText(/Picking a Hive points this page at it/)).toBeInTheDocument();
  });
});

// "Clicking links on the website produces weird links: http://host/?admin#travel". `?admin` decides the view and
// the page navigates by hash, so the parameter outlived every click and the URL ended up claiming two views.
// One rule for `?admin` and `?hub=`: the address decides the view, and no address claims both.
describe("the address and the view agree", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.setItem("adobee-hub", "local");
    window.history.replaceState(null, "", "/");
    vi.spyOn(api, "health").mockResolvedValue({ llm: "mock", model: "", fast_model: "" } as never);
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "demand").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "adminOverview").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "adminNeighbours").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "directory").mockRejectedValue(new Error("offline"));
  });

  afterEach(() => window.history.replaceState(null, "", "/"));

  const app = () =>
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

  it("still opens the hub's own panel with ?admin", () => {
    window.history.replaceState(null, "", "/?admin");
    app();
    expect(screen.getByLabelText(en["admin.password"])).toBeInTheDocument();
  });

  it("leaves admin mode, and the address, when an in-app link is followed", async () => {
    window.history.replaceState(null, "", "/?admin");
    app();
    expect(screen.getByLabelText(en["admin.password"])).toBeInTheDocument();

    // What a click on the nav's "Agent network" does: the hash changes, the query does not.
    window.history.replaceState(null, "", "/?admin#travel");
    window.dispatchEvent(new HashChangeEvent("hashchange"));

    expect(await screen.findByLabelText(en["agent.intent"])).toBeInTheDocument();
    expect(window.location.search).not.toContain("admin");
    expect(screen.queryByLabelText(en["admin.password"])).toBeNull();
  });

  it("resolves a pasted hybrid address to one view rather than both", async () => {
    window.history.replaceState(null, "", "/?admin#travel");
    app();

    // Admin was asked for, so admin is what renders; the anchor belonged to a page nobody is looking at.
    expect(screen.getByLabelText(en["admin.password"])).toBeInTheDocument();
    expect(screen.queryByLabelText(en["agent.intent"])).toBeNull();
    await waitFor(() => expect(window.location.hash).toBe(""));
    expect(window.location.search).toContain("admin");
  });

  it("leaves admin mode when the brand is clicked, like any other link home", async () => {
    window.history.replaceState(null, "", "/?admin");
    app();
    window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;

    await userEvent.click(screen.getByRole("link", { name: "Adobee Hive" }));

    expect(await screen.findByLabelText(en["agent.intent"])).toBeInTheDocument();
    expect(window.location.search).not.toContain("admin");
  });

  it("keeps the other parameters, spelled the way they were written", async () => {
    window.history.replaceState(null, "", "/?demo&admin");
    app();

    window.history.replaceState(null, "", "/?demo&admin#business");
    window.dispatchEvent(new HashChangeEvent("hashchange"));

    await waitFor(() => expect(window.location.search).toBe("?demo"));
    expect(window.location.search).not.toBe("?demo=");
  });

  it("goes back to the finder, not to a hybrid, when the hub is dropped", async () => {
    sessionStorage.setItem("adobee-hub", "a");
    window.history.replaceState(null, "", "/?hub=a&demo#travel");
    app();

    await userEvent.click(screen.getByRole("button", { name: en["finder.change"] }));

    expect(await screen.findByRole("heading", { name: en["finder.title"] })).toBeInTheDocument();
    expect(window.location.search).toBe("?demo");
    expect(window.location.hash).toBe("#travel");
  });

  it("follows the back button instead of leaving the view behind", async () => {
    window.history.replaceState(null, "", "/?admin");
    app();
    expect(screen.getByLabelText(en["admin.password"])).toBeInTheDocument();

    window.history.replaceState(null, "", "/");
    window.dispatchEvent(new PopStateEvent("popstate"));

    expect(await screen.findByLabelText(en["agent.intent"])).toBeInTheDocument();
  });
});

// The chosen Hive has to be visible and has to survive a reload, and an unreachable one must never be a dead page.
describe("the Hive the app is on", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.clear();
    window.history.replaceState(null, "", "/");
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "demand").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "adminOverview").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "adminNeighbours").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "directory").mockRejectedValue(new Error("offline"));
  });

  const app = () =>
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

  it("says which Hive it is on, where a person can always see it", async () => {
    sessionStorage.setItem("adobee-hub", "zurich");
    vi.spyOn(api, "health").mockResolvedValue({ llm: "mock", model: "", fast_model: "" } as never);
    app();

    expect(await screen.findByText(en["nav.onHub"].replace("{hub}", "zurich"))).toBeInTheDocument();
  });

  it("keeps the chosen Hive, and where it answers, across a reload", async () => {
    setChosenHub("zurich", "http://10.0.0.2:8461");
    vi.spyOn(api, "health").mockResolvedValue({ llm: "mock", model: "", fast_model: "" } as never);

    const { unmount } = app();
    expect(await screen.findByText(en["nav.onHub"].replace("{hub}", "zurich"))).toBeInTheDocument();
    unmount();

    app();
    expect(await screen.findByText(en["nav.onHub"].replace("{hub}", "zurich"))).toBeInTheDocument();
    expect(apiBase()).toBe("http://10.0.0.2:8461");
  });

  it("says a Hive could not be reached, and offers the way back, instead of a dead page", async () => {
    setChosenHub("ghost", "http://10.0.0.9:8499");
    vi.spyOn(api, "health").mockRejectedValue(new Error("error.offline"));
    app();

    expect(await screen.findByText(en["app.hubUnreachable"])).toBeInTheDocument();
    const back = screen.getAllByRole("button", { name: en["finder.change"] })[0];
    await userEvent.click(back);

    expect(await screen.findByRole("heading", { name: en["finder.title"] })).toBeInTheDocument();
    expect(apiBase()).toBe("");
  });

  it("goes back to the build's own backend when the Hive is dropped", async () => {
    setChosenHub("zurich", "http://10.0.0.2:8461");
    vi.spyOn(api, "health").mockResolvedValue({ llm: "mock", model: "", fast_model: "" } as never);
    app();

    await userEvent.click(screen.getAllByRole("button", { name: en["finder.change"] })[0]);

    expect(await screen.findByRole("heading", { name: en["finder.title"] })).toBeInTheDocument();
    expect(apiBase()).toBe("");
    expect(sessionStorage.getItem("adobee-hub-url")).toBeNull();
  });
});
