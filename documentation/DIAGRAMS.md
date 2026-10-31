# Diagrams

Four pictures of what runs on `main`, for anyone joining the work: where each part is hosted, how a request
becomes a signed booking, how a question about any business finds an answer, and where the data lives. They are
Mermaid, so GitHub draws them and anyone can edit them as text. Change a picture in the same PR as the code it
shows; `tests/test_docs.py` fails when one names a file, MCP tool or endpoint that does not exist.

Clay marks the one step only a person can take: **Approve**. Every table of modules, tools and endpoints is in
[ARCHITECTURE.md](ARCHITECTURE.md); how to start and test each part is in the [developer guide](DEVELOPER.md).

## 1. The system

Two free hosts, one repo. A push to `main` redeploys both. The backend serves people over REST and agents over
MCP, from the same signed Hive cards.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#fffefb", "primaryBorderColor": "#857c6f", "primaryTextColor": "#17140f", "lineColor": "#857c6f", "clusterBkg": "#f6f3ed", "clusterBorder": "#e4ded3", "noteBkgColor": "#f6f3ed", "noteBorderColor": "#e4ded3", "actorBkg": "#fffefb", "actorBorder": "#857c6f", "signalColor": "#4b443a", "signalTextColor": "#17140f", "fontFamily": "Helvetica, Arial, sans-serif"}}}%%
flowchart LR
  classDef person fill:#a24f2c,stroke:#5a2e1a,color:#fffefb
  classDef host fill:#fffefb,stroke:#857c6f,color:#17140f
  classDef model fill:#f6f3ed,stroke:#857c6f,color:#4b443a,stroke-dasharray:4 3

  G([Guest]):::person
  O([Business owner]):::person
  X([Any MCP client]):::person

  subgraph GH["GitHub"]
    REPO[reactbias/Adobee-Hive<br/>main]:::host
    CI[ci.yml<br/>ruff · pytest · vitest · build]:::host
    PAGES[deploy-frontend-pages.yml]:::host
    WARM[keep-backend-warm.yml<br/>every 10 min]:::host
  end

  subgraph WEB["GitHub Pages"]
    UI[React app<br/>Agent network · Business<br/>?demo adds presenter tools]:::host
  end

  subgraph RENDER["Render, Frankfurt"]
    API[FastAPI · main.py<br/>REST /api · MCP /mcp/]:::host
    DUCK[(DuckDB file<br/>on the instance)]:::host
    PG[(Postgres<br/>adobee-hive-db)]:::host
  end

  LLM[OpenAI · gpt-5-mini<br/>offline fallback without a key]:::model
  NET[Public web<br/>OpenAI web search or OpenStreetMap]:::model

  G --> UI
  O --> UI
  UI -->|REST| API
  X -->|MCP| API
  API --- DUCK
  DUCK -.->|snapshot after each write<br/>restore on boot| PG
  API -.-> LLM
  API -.->|scout only| NET
  REPO --> CI
  REPO --> PAGES --> UI
  REPO -->|render.yaml autoDeploy| API
  WARM -->|GET /api/health| API
```

Inside the backend, one Hive core sits under both doors. The REST endpoints call the agents; the agents reach the
Hive only as MCP clients, the same way an outside agent would.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#fffefb", "primaryBorderColor": "#857c6f", "primaryTextColor": "#17140f", "lineColor": "#857c6f", "clusterBkg": "#f6f3ed", "clusterBorder": "#e4ded3", "noteBkgColor": "#f6f3ed", "noteBorderColor": "#e4ded3", "actorBkg": "#fffefb", "actorBorder": "#857c6f", "signalColor": "#4b443a", "signalTextColor": "#17140f", "fontFamily": "Helvetica, Arial, sans-serif"}}}%%
flowchart TB
  classDef core fill:#17140f,stroke:#17140f,color:#f6f3ed
  classDef mod fill:#fffefb,stroke:#857c6f,color:#17140f
  classDef guard fill:#f6f3ed,stroke:#a24f2c,color:#5a2e1a

  REST[REST · main.py]:::mod
  MCP[MCP server · mcp_server.py<br/>+ domains: explore.py · scout.py · hr.py]:::mod

  subgraph AGENTS["Three agents, one group chat"]
    A[Your agent · agent.py<br/>OpenAI tool loop or scripted planner]:::mod
    V[Verifier · second_opinion.py<br/>model or rule check]:::mod
    C[Critic · critic.py<br/>no model, argues the alternative]:::mod
  end

  INJ[injection.py<br/>withholds text aimed at agents]:::guard
  GRD[guard.py<br/>tokens and rate limits]:::guard
  OWN[owner.py<br/>plain words to a signed version]:::mod
  HIVE[Hive core · hive.py<br/>cards · Ed25519 signatures · ranking · receipts · demand]:::core
  DB[db.py · storage.py]:::mod

  REST --> GRD
  REST --> A
  A -->|MCP client| INJ --> MCP
  A --> V
  A --> C
  REST --> OWN --> HIVE
  MCP --> HIVE
  REST --> HIVE
  HIVE --> DB
```

## 2. A booking, from question to receipt

What happens when a guest types "a quiet room near SBB for two nights" in chapter 1. Nothing is booked until the
guest presses Approve; the agent holds the `hive_book` call on the server, and the button sends exactly that call,
once.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#fffefb", "primaryBorderColor": "#857c6f", "primaryTextColor": "#17140f", "lineColor": "#857c6f", "clusterBkg": "#f6f3ed", "clusterBorder": "#e4ded3", "noteBkgColor": "#f6f3ed", "noteBorderColor": "#e4ded3", "actorBkg": "#fffefb", "actorBorder": "#857c6f", "signalColor": "#4b443a", "signalTextColor": "#17140f", "fontFamily": "Helvetica, Arial, sans-serif"}}}%%
sequenceDiagram
  autonumber
  actor Guest
  participant UI as React app
  participant API as FastAPI
  participant AG as Your agent
  participant MCP as Hive MCP
  participant V as Verifier
  participant C as Critic

  Guest->>UI: types the request
  UI->>API: POST /api/agent
  API->>AG: run, in the page's language
  AG->>MCP: hive_discover
  MCP-->>AG: ranked matches, score breakdown, who was left out and why
  AG->>MCP: hive_get_card
  MCP-->>AG: signed card
  Note over AG: checks the signature against the owner's pinned key
  AG->>MCP: hive_check_availability
  MCP-->>AG: free units and total
  Note over AG: holds hive_book, does not send it
  AG->>V: check the hold against the request and the card
  AG->>C: argue for the strongest alternative
  V-->>API: agree or object
  C-->>API: agree or concede
  API-->>UI: reply, held booking, consensus
  UI-->>Guest: group chat, then the Approve card
  rect rgba(162, 79, 44, 0.18)
    Guest->>UI: Approve
    UI->>API: POST /api/agent/approve
    API->>MCP: hive_book, exactly as held
    MCP-->>API: signed receipt, pins the card version
  end
  API-->>UI: booking
  UI-->>Guest: receipt and next steps
```

Without a key, or when OpenAI fails or times out, the scripted planner makes the same MCP calls and the verifier
uses its rule check, so the demo never stops. Card text reaches the agent as data, after `injection.py`.

## 3. A question about any business

When the question is not about a room, the app asks the Hive's other cards. If none covers it, the agents look on
the public web, verify what they find and add it as an unclaimed card, in the same conversation.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#fffefb", "primaryBorderColor": "#857c6f", "primaryTextColor": "#17140f", "lineColor": "#857c6f", "clusterBkg": "#f6f3ed", "clusterBorder": "#e4ded3", "noteBkgColor": "#f6f3ed", "noteBorderColor": "#e4ded3", "actorBkg": "#fffefb", "actorBorder": "#857c6f", "signalColor": "#4b443a", "signalTextColor": "#17140f", "fontFamily": "Helvetica, Arial, sans-serif"}}}%%
sequenceDiagram
  autonumber
  actor Guest
  participant UI as React app
  participant API as FastAPI
  participant EX as Explore
  participant SC as Scout
  participant W as Public web

  Guest->>UI: asks about any business
  Note over UI: route.ts picks room or any business
  UI->>API: POST /api/ask
  API->>EX: which cards cover this?
  Note over EX: card text and topics, plus a model relevance check when a key is set
  alt a card covers it
    EX-->>UI: answers from signed cards, action held
    rect rgba(162, 79, 44, 0.18)
      Guest->>UI: Approve
      UI->>API: POST /api/ask/approve
    end
    API-->>UI: hand-off to the business
  else nothing covers it
    EX-->>UI: no card, counted as demand
    UI->>API: POST /api/ask/scout
    API->>SC: find real businesses
    SC->>W: search, then fetch each site
    Note over SC: keeps only what the business's own site confirms
    SC-->>API: unclaimed cards, signed by the Hive as compiler
    API-->>UI: answer from the new cards
  end
```

Unclaimed cards say so in every answer, owner edits refuse them, and approving only hands the person off to the
business's own site.

## 4. Where the data lives

One DuckDB file holds every card version, booking, review and demand count. The free Render disk is wiped on
every deploy, so with `DATABASE_URL` set the whole file is copied to Postgres after each write and copied back on
boot. Locally there is no Postgres; the file in `code/backend/data/` just stays.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#fffefb", "primaryBorderColor": "#857c6f", "primaryTextColor": "#17140f", "lineColor": "#857c6f", "clusterBkg": "#f6f3ed", "clusterBorder": "#e4ded3", "noteBkgColor": "#f6f3ed", "noteBorderColor": "#e4ded3", "actorBkg": "#fffefb", "actorBorder": "#857c6f", "signalColor": "#4b443a", "signalTextColor": "#17140f", "fontFamily": "Helvetica, Arial, sans-serif"}}}%%
flowchart TB
  classDef step fill:#fffefb,stroke:#857c6f,color:#17140f
  classDef store fill:#17140f,stroke:#17140f,color:#f6f3ed
  classDef warn fill:#f6f3ed,stroke:#a24f2c,color:#5a2e1a

  subgraph BOOT["Boot · main.py lifespan"]
    B1{DuckDB file<br/>on disk?}:::step
    B2{DATABASE_URL<br/>set?}:::step
    B3[storage.restore<br/>write the last snapshot to disk]:::step
    B4[Postgres unreachable:<br/>run on the seed, snapshots off]:::warn
    B5{Hive empty?}:::step
    B6[hive_seed.seed_if_empty<br/>fictional Basel businesses]:::step
    B7([serving]):::step
    B1 -- yes --> B5
    B1 -- no --> B2
    B2 -- no --> B5
    B2 -- yes --> B3 --> B5
    B3 -. fails .-> B4 --> B5
    B5 -- yes --> B6 --> B7
    B5 -- no --> B7
  end

  subgraph WRITE["Every write · db.write"]
    W1[hive.publish · booking · review · demand]:::step
    W2[(DuckDB)]:::store
    W3[storage.snapshot<br/>background thread, bursts coalesced]:::step
    W4[(Postgres<br/>one row, latest wins)]:::store
    W1 --> W2 --> W3 --> W4
  end

  B7 --> W1
```

Held bookings and held hand-offs stay in memory for 30 minutes; a restart only means asking the agent again. Every
card change goes through `hive.publish`, which signs the new version and keeps the old ones, so a receipt can always
show what was promised. `POST /api/demo/reset` goes back to the seed cards.

## Who works where

The pictures double as a map of the lanes in [CONTRIBUTING.md](../CONTRIBUTING.md). Pick a box, open its file,
find its test.

| Box | Code | Tests |
| --- | --- | --- |
| React app | `code/frontend/src` | `npm test`: `TravellerAgent.test.tsx`, `OwnerPanel.test.tsx`, `route.test.ts` |
| FastAPI, REST, docs | `main.py` | `test_docs.py`, `test_promises.py` |
| Hive MCP, booking | `mcp_server.py`, `hive.py` | `test_hive.py`, `test_promise.py`, `test_tool_errors.py` |
| Your agent, verifier, critic | `agent.py`, `second_opinion.py`, `critic.py` | `test_critic.py`, `test_injection.py`, `test_languages.py` |
| Any business, scout | `explore.py`, `scout.py` | `test_explore.py`, `test_relevance.py`, `test_scout.py` |
| Owner studio | `owner.py`, `waiting.py` | `test_owner_languages.py`, `test_waiting.py`, `test_card_stats.py` |
| Data | `db.py`, `storage.py`, `hive_seed.py` | `test_persist.py` |
| Hosting | `render.yaml`, `.github/workflows/` | CI on every PR |
