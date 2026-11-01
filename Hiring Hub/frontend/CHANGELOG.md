# Adobee Hive Recruitment Portal - Changes Log

All notable changes, implementation tasks, and file updates for the Adobee Hive Talent Intelligence Platform are documented in this file.

### [1.2.2] - 2026-11-01

### Header UI Cleanup & Brand Alignment
- **Brand Logo & Favicon**:
  - Saved official open-hexagon clay bee mark from `https://reactbias.github.io/Adobee-Hive/brand/logo.svg` to [public/brand/logo.svg](file:///f:/Projects/adobee%20hiver/adobee-hiver/frontend/public/brand/logo.svg).
  - Updated [src/components/layout/Header.tsx](file:///f:/Projects/adobee%20hiver/adobee-hiver/frontend/src/components/layout/Header.tsx) to render `/brand/logo.svg` in place of legacy amber polygon SVG.
  - Updated [index.html](file:///f:/Projects/adobee%20hiver/adobee-hiver/frontend/index.html) favicon to `/brand/logo.svg`.
- **Top Search Bar & Pipeline Badge Removal**:
  - Removed top search input (`Search candidates... ⌘K`) and associated hotkey handlers from [Header.tsx](file:///f:/Projects/adobee%20hiver/adobee-hiver/frontend/src/components/layout/Header.tsx) as requested.
  - Removed `Pipeline: Live Analyzer Sync` status indicator from header.

### Light Theme Matching (https://reactbias.github.io/Adobee-Hive/)
- **CSS Design Tokens ([src/index.css](file:///f:/Projects/adobee%20hiver/adobee-hiver/frontend/src/index.css))**:
  - Synchronized `:root` palette tokens with reference design system:
    - Pure white surfaces: `--color-background: 255 255 255`, `--color-surface: 255 255 255`
    - Warm light surfaces: `--color-surface-dim: 247 247 245` (`#f7f7f5`), `--color-surface-container: 241 241 238` (`#f1f1ee`)
    - Crisp borders: `--color-surface-container-high: 230 231 227` (`#e6e7e3`), `--color-surface-container-highest: 207 209 204` (`#cfd1cc`)
    - Ink typography: `--color-on-surface: 22 24 29` (`#16181d`), `--color-on-surface-variant: 91 96 107` (`#5b606b`)
    - Brand honey & clay accents: `--color-primary: 217 154 30` (`#d99a1e`), container tint: `251 241 217` (`#fbf1d9`), clay accent: `#a24f2c`
    - Semantic success: `--color-tertiary: 31 122 77` (`#1f7a4d`)
- **Tailwind Tokens ([tailwind.config.js](file:///f:/Projects/adobee%20hiver/adobee-hiver/frontend/tailwind.config.js))**:
  - Aligned fixed tokens (`primary-fixed: #fbf1d9`, `primary-fixed-dim: #d99a1e`, `inverse-primary: #f2b63c`, `error: #b3261e`).
- **Glassmorphism & Theme Init ([src/index.css](file:///f:/Projects/adobee%20hiver/adobee-hiver/frontend/src/index.css), [src/main.tsx](file:///f:/Projects/adobee%20hiver/adobee-hiver/frontend/src/main.tsx))**:
  - Adapted `.glass-panel` for clean light mode backdrop (`rgba(255, 255, 255, 0.85)`).
  - Defaulted application to light mode on initial load unless `'dark'` is stored in `localStorage`.

### [1.2.1] - 2026-11-01

### PostgreSQL Role Authentication & Database Resolution (`db`, `backend`)
- **Root Cause**: The named Docker volume `pgdata` was previously initialized with the superuser role `admin`. When `backend` started with `DATABASE_URL` configured for `postgres:postgres`, PostgreSQL rejected the connection with `FATAL: Role "postgres" does not exist`.
- **Resolution**: Provisioned superuser role `postgres` with password `postgres` in the running cluster without data loss (`CREATE ROLE postgres WITH SUPERUSER LOGIN PASSWORD 'postgres';`).
- **Verified**: `backend-1` connected cleanly, ran `init_db()` migrations, and started listening on `http://0.0.0.0:8000`. Confirmed `HTTP 200` on both `http://localhost:8000/docs` and `http://localhost:3000`.

### Frontend Code Audit & Error Remediation
- **Safe Property Access**:
  - `CandidatePoolView.tsx`: Added safe optional chaining on `requisition?.hiringLead?.name` preventing `TypeError` on unseeded/loading states; added default requisition auto-selection on mount.
  - `DossierView.tsx` & `DossierNotes.tsx`: Added safe chaining on `telemetry?.atsMetadata?....` and synchronized notes list on candidate transition.
  - `CodeAuditCard.tsx`: Safely accessed `telemetry?.codeRepo` and removed hardcoded Elena Rostova statistics in favor of neutral telemetry fallbacks.
  - `CandidateCard.tsx`: Safely defaulted `candidate.education` before `.split('(')[0]`.
  - `CandidateHeaderBanner.tsx`: Replaced hardcoded subtitle with `{candidate.title || 'Candidate'} • {candidate.currentCompany}`.
- **API & Query Robustness (`src/services/api.ts`)**:
  - Guarded `saveChatSession` and `fetchChatSession` against empty/whitespace position IDs.
  - Added React Query `enabled: Boolean(...)` guards to `useRequisition`, `useCandidates`, and `useCandidate`.
- **UI & Visualization Refinements**:
  - `JobPostingsView.tsx`: Relocated collapsible "Add Job Posting" form into a dedicated specification card cleanly positioned above department tabs.
  - `SourcingDonut.tsx`: Replaced hardcoded SVG circle offsets with dynamically computed arc segments based on `sourcingChannels`.
  - `main.tsx`: Synchronized initial theme class from `localStorage` preference on boot.
- **Test Suite Verification**:
  - `App.test.tsx`: Mocked `ensureOrganization` and used asynchronous `findByText` selectors. All 5 unit tests across `App.test.tsx` and `CopilotChat.test.tsx` now pass cleanly.

### Frontend TypeScript Build Fixes (`types/index.ts`, `Sidebar.tsx`)
- **`types/index.ts`**: Added missing `AnalyticsKPIs` type definition required by `KpiSummaryGrid.tsx`.
- **`types/index.ts`**: Added optional properties (`phone`, `country`, `companies`, `highest_education_level`, `technical_skills`) to `BackendCandidateBrief` interface to align with candidate transformation helper.
- **`Sidebar.tsx`**: Corrected `useRequisitions` hook return value destructuring from `{ requisitions }` to `{ data: requisitions = [] }`.
- **Build Verified**: Verified clean compilation via `npx tsc --noEmit` and production build via `npm run build` (vite v5.4.21).

### Docker Compose & Environment Configuration (`.env`)
- **Root `.env` Configuration**: Populated root `.env` with required PostgreSQL variables (`POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`, `POSTGRES_DB=hr_database`) resolving the interpolation failure during `docker compose up --build`.
- **Interpolation Verified**: Confirmed configuration via `docker compose config` with `DATABASE_URL` resolved to `postgresql+psycopg://postgres:postgres@db:5432/hr_database`.

### Remote Branch Merge & Conflict Resolution (`JobPostingsView.tsx`, `api.ts`)
- **Remote Integration**: Resolved Git merge conflict between local remediation branch and `origin/sb_hack`.
- **`frontend/src/services/api.ts`**: Merged remote `createPosition` API endpoint (`POST /positions`) and `CreatePositionData` payload type while keeping zero-mock data integrity and proper error propagation.
- **`frontend/src/components/jobPostings/JobPostingsView.tsx`**: Merged "Add Job Posting" modal form and React Query cache invalidation (`queryClient.invalidateQueries({ queryKey: ['requisitions'] })`) into the styled, responsive, zero-mock UI.
- **Commit History**: Cleanly committed and merged (`897ba3d` and `c4ad3ef`).

## [1.2.0] - 2026-10-31

### Complete Frontend Remediation & Mock Data Elimination
- **Mock Data Elimination & API Layer Overhaul (`frontend/src/services/api.ts`)**:
  - Severed all imports and fallback paths to `mockData.ts` (`mockRequisitions`, `mockCandidates`, `mockFunnelStages`, etc.).
  - `useRequisitions`: Returns real data from backend `/positions` or an empty array `[]` on error/unseeded database (no mock fallback roles).
  - `useCandidate`: Direct fetch from `/cvs/{numericId}`, returning `Candidate | undefined` (no mock fallback to `mockCandidates[0]`).
  - `useAdvanceCandidateStage`: Stage updates persist in client `localStorage` under `hive_stage_overrides` instead of mutating in-memory mock objects.
  - `useAnalytics`: Live aggregation of metrics from `/positions` (total pipeline, processed candidates, pending analysis) instead of hardcoded numbers.
  - `mapBackendCandidateToCandidate`: Mapped real fields (`brief.companies?.[0]`, `brief.highest_education_level`, `'Not specified'` for missing fields) instead of fabricated values (`'$190k - $220k'`, `'Verified Enterprise'`).
- **Non-Blocking Toast System (`frontend/src/context/ToastContext.tsx`, `App.tsx`)**:
  - Implemented lightweight, non-blocking toast notification provider supporting `'info'`, `'success'`, `'error'`, and `'warning'` alerts with automatic dismiss.
  - Replaced all 8 native browser `alert()` modal calls across `DossierView.tsx`, `CandidateCard.tsx`, `CandidatePoolView.tsx`, and `AnalyticsView.tsx`.
- **CSS Variable Theme Engine & Light/Dark Switcher (`tailwind.config.js`, `src/index.css`, `Header.tsx`)**:
  - Converted Tailwind color tokens (`primary`, `secondary`, `tertiary`, `surface-*`, `background`, etc.) to use CSS variables with alpha-channel support: `rgb(var(--color-...) / <alpha-value>)`.
  - Added full light-mode and dark-mode color variable tokens to `src/index.css` (`:root` for light mode and `.dark` for Obsidian dark mode).
  - Added theme toggle button to `Header.tsx` with `localStorage` persistence and automatic class toggle on `document.documentElement`.
- **Mobile Responsive Drawer Layout (`Header.tsx`, `Sidebar.tsx`, `NavigationContext.tsx`, `App.tsx`)**:
  - Added mobile menu state (`isMobileMenuOpen`, `setIsMobileMenuOpen`) in `NavigationContext`.
  - Added hamburger toggle button in `Header.tsx` on viewports `< lg`.
  - Converted `Sidebar.tsx` into a responsive slide-out drawer on small screens with backdrop overlay and auto-closing on navigation.
  - Dynamically wired `Job Postings` badge count in `Sidebar.tsx` to `useRequisitions()`.
  - Made main container padding responsive (`lg:pl-64 pl-0`).
- **Component Decomposition & Modularization (`src/components/dossier/`, `src/components/analytics/`)**:
  - Decomposed monolithic `DossierView.tsx` (593 lines) into 6 isolated components: `ApplicantPoolRail.tsx`, `CandidateHeaderBanner.tsx`, `TelemetryScorecards.tsx`, `CodeAuditCard.tsx`, `EmploymentTimeline.tsx`, and `DossierNotes.tsx`.
  - Decomposed monolithic `AnalyticsView.tsx` (526 lines) into 5 focused components: `KpiSummaryGrid.tsx`, `FunnelProgression.tsx`, `DepartmentDistribution.tsx`, `SourcingDonut.tsx`, and `QueryLogsTable.tsx`.
- **UI Clean-up, Roadmap Clarity & Empty States**:
  - `SettingsView.tsx`: Clarified mock integrations (`Greenhouse`, `Checkr`, `The Work Number`) with a "Roadmap Preview / Upcoming" badge to eliminate misleading live webhook claims.
  - `Sidebar.tsx`: Replaced hardcoded "US-EAST-AI-01" cluster label with dynamic "Docker Cluster".
  - `DepartmentTabs.tsx`: Restored all department tabs (`All Departments`, `Engineering`, `Product & Design`, `Sales & Marketing`, `Data & AI`).
  - `JobPostingsView.tsx`: Removed fake `"Sync Active: 14 Nodes"` marketing copy; added empty state for search queries and unseeded states.
  - `CandidateCard.tsx`: Removed hardcoded `+ OSS Contributor (5k stars)` tag from hero card.
  - `CopilotChat.tsx`: Removed hardcoded `'Sarah Jenkins'` message sender (replaced with `'Recruiter'`) and removed dead/unhandled icon buttons.
  - `AnalyticsView.tsx`: Replaced hardcoded "1,280" with dynamic `kpis.totalPipeline`; added empty states for department quality, sourcing channels, and natural language queries.
  - `DossierView.tsx`: Applicant pool rail dynamically connects to `useCandidates(selectedRequisitionId)`; empty state added when candidate is not found.
- **Test Decoupling**:
  - `frontend/src/tests/App.test.tsx`: Decoupled candidate search assertion from hardcoded mock candidate name `'Dr. Elena Rostova'`, asserting on UI landmark `Filtered Pool`.
  - `frontend/e2e/recruiter.spec.ts`: Made candidate and requisition assertions conditional and resilient to live database content.

## [1.1.0] - 2026-10-31

### Backend API Integration (`cv_analyzer`)
- **FastAPI CORS & Docker Enhancements**:
  - `backend/cv_analyzer/api.py`: Attached `CORSMiddleware` supporting browser requests from `localhost:3000` and container environments.
  - `backend/Dockerfile`: Fixed CMD from `main:app` to `cv_analyzer.api:app`.
  - `backend/requirements.txt`: Populated all production backend dependencies from `environment.yml`.
- **Frontend Reverse Proxy & Environment**:
  - `frontend/vite.config.ts`: Added `/api` proxy targeting `http://127.0.0.1:8000` with rewrite to streamline local dev without CORS blocks.
  - `frontend/src/vite-env.d.ts`: Added TypeScript declarations for `VITE_API_URL`, `VITE_API_KEY`, and `VITE_ADMIN_TOKEN`.
  - `.gitignore`: Created root ignore file covering `node_modules/`, `dist/`, `__pycache__/`, `*.pyc`, and `.env`.
- **API Contracts & Type Definitions**:
  - `frontend/src/types/index.ts`: Added `BackendPosition`, `BackendCandidateBrief`, `BackendFilterResponse`, and `BackendCVDossier` contracts.
- **Service Layer Overhaul**:
  - `frontend/src/services/api.ts`:
    - Implemented `fetchWithAuth<T>()` with automated `x-api-key` header injection.
    - Implemented `bootstrapOrganization()` for zero-friction provisioning of default "Adobee Hive" organization key.
    - Upgraded `useRequisitions()` to fetch active positions from `GET /positions` with robust fallback to `mockRequisitions` if database is unseeded.
    - Upgraded `useCandidates()` to fetch candidate briefs from `GET /positions/{id}/candidates` with data adaptation to `Candidate`.
    - Upgraded `useCandidate()` to fetch deep CV extractions from `GET /cvs/{doc_id}`.
    - Added `useRecruiterFilter()` and `useResetRecruiterFilter()` mutations for the backend LLM Recruiter Agent (`POST /positions/{id}/filter` and `POST /positions/{id}/filter/reset`).
    - Added `useReprocessCandidateCV()` mutation for `POST /cvs/{doc_id}/reprocess`.
- **View Integration**:
  - `JobPostingsView.tsx`: Displays live active positions from `GET /positions` with dynamic headcount, total talent metrics, and live sync badge; excluded requisition creation per user specification.
  - `CopilotChat.tsx`: Connected natural language recruiter queries to `useRecruiterFilter()` mutation, updating candidate roster and criteria tokens with real LLM reasoning; connected reset to `useResetRecruiterFilter()`.
  - `DossierView.tsx`: Connected to `useReprocessCandidateCV()` to queue background re-extraction of CV documents.
  - `SettingsView.tsx`: Added Backend CV Analyzer Connection card with live connection testing, manual API key override, and one-click organization auto-provisioning.

## [1.0.0] - 2026-10-31

### Design & Theme Integration
- **Obsidian Hive Precision Design System**:
  - Implemented authentic Stitch design theme (`projects/17365583965999936411`).
  - Colors: Cosmic obsidian `#090D16` / `#0F131C` / `#181B25` / `#1C1F29` / `#262A34`, Honey Amber primary `#F59E0B`, Electric Cyan secondary `#38BDF8`, Emerald tertiary `#10B981`, and Slate neutral typography.
  - Typography: Loaded `Geist` (headlines/display), `Inter` (body), and `JetBrains Mono` (metrics/labels/tokens), plus Google `Material Symbols Outlined`.

### Core Views Implemented
1. **Job Postings Directory (`JobPostingsView.tsx`)**:
   - Requisition orchestration command center with live KPI metric strip (Open Roles, Total Talent, Shortlisted, In Interview).
   - Department selector tabs: All Departments (18), Engineering (8), Product & Design (4), Sales & Marketing (3), Data & AI (3).
   - Search & Status bar with multi-state filters (Active, Urgent, Draft, Closed) and AI fit index sort.
   - Bento grid with featured lead requisition card (`Lead Full-Stack AI Engineer`, Req #AH-2049) and urgent/active role cards with hiring lead portraits, skill chips with live beacons, pipeline distribution counters, and direct candidate pool routing.
   - Bottom macro-efficiency metrics bar (Mean Time-to-Hire 18.4d, Offer Acceptance 91.8%, Sourcing Yield 2.4x).
2. **Candidate Pool & AI Co-pilot Filter (`CandidatePoolView.tsx`)**:
   - 100vh locked workbench with dual independent scrolling panes.
   - Left Column: `CopilotChat.tsx` with multi-turn prompt interaction, live competency synthesis bars (RAG 4/6, OSS 2/6), dismissible NL criteria vector chips (`Exp: 5+ yrs`, `Domain: RAG / LLM`, `Location: SF Hybrid`, `Match > 85%`), and quick prompt pills.
   - Right Column: Ranked candidate roster featuring Dr. Elena Rostova hero card (98% Overall Fit, Stanford Ph.D., Scale AI/Anthropic, verified check, compensation alignment) and secondary candidate cards.
3. **Candidate Backend Dossier (`DossierView.tsx`)**:
   - Single-source-of-truth technical telemetry view with applicant pool switcher rail and embedding cosine fit meter (0.984).
   - Candidate credentials, work authorization (US Citizen), 2-week notice period, GitHub and LinkedIn links.
   - Algorithmic evaluation breakdown dials: System Architecture (9.8/10), LLM/RAG (9.9/10), TypeScript/Python Async (9.6/10).
   - Automated AI code repository audit: 1,420 commits in 2024, 118 commits/mo, 4.8k stars, 0.02 pristine architecture smell.
   - The Work Number API employment history verification for Scale AI and Stripe.
   - Greenhouse ATS integration metadata, compensation alignment verification ($205k - $225k base), and stage progression workflow.
4. **Talent Intelligence Analytics (`AnalyticsView.tsx`)**:
   - Executive overview KPI cards (Total Active Pipeline 1,280, Avg Time to Fill 18.4d, AI Screening Accuracy 96.2%, Offer Acceptance Rate 91.8%).
   - Requisition Funnel Progression (Sourced 1,280 → AI Filtered 624 → First Round 248 → Technical Loop 94 → Executive Review 28 → Offer Extended 12).
   - Department Quality Distribution percentiles across Engineering, Product, GTM, and Design.
   - Circular SVG Donut chart attributing candidate sourcing channels (Direct 42%, AI Auto Inbound 31%, Referrals 18%, Exec Search 9%).
   - Top AI Natural Language Queries log with retrieval metrics and match accuracy.
5. **Settings & Cluster Configuration (`SettingsView.tsx`)**:
   - ATS platform webhooks (Greenhouse, Checkr, The Work Number).
   - Neural matcher model temperature and algorithmic weight calibration.

### Testing & Verification
- **Vitest Unit & Component Tests**: 5/5 passing tests in `App.test.tsx` and `CopilotChat.test.tsx`.
- **Playwright End-to-End Tests**: 1/1 passing full user journey test in `e2e/recruiter.spec.ts`.
- **Vite Production Bundle**: Zero-error compilation in `dist/`.
