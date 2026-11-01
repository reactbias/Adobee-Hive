# Adobee Hive Frontend Code Review: Hardcoded Data, Mock Fallbacks & Design Audit

**Audit Date:** October 31, 2026  
**Audited Repository:** `adobee-hiver/frontend`  
**Scope:** Architecture, API Services, Component Architecture, Design System, Mock & Hardcoded Data Inventory, UI/UX Improvements, and Testing.

---

## 1. Executive Summary

The **Adobee Hive** frontend is designed as an "Obsidian Hive Precision" talent intelligence platform. It features an aesthetic dark-mode layout with amber (`#f59e0b`), cyan (`#38bdf8`), and emerald (`#10b981`) accents, inspired by advanced recruiter tooling and agentic AI workflows.

While recent pull requests successfully connected the core backend endpoints (`GET /positions`, `POST /positions/{id}/cvs`, `POST /positions/{id}/filter`, `POST /cvs/{id}/reprocess`, and `GET /chat-sessions`), a thorough audit reveals that **substantial legacy mock data and synthetic fallbacks have resurfaced or remain embedded in the frontend layer**. Furthermore, several UI elements across the application are static illusions (hardcoded metrics, dead buttons, unpersisted toggles, and browser `alert()` popups), and the design system lacks true light/dark mode adaptability and mobile responsiveness.

This document provides a line-by-line audit of all hardcoded values, mock data remnants, design shortcomings, and actionable architectural recommendations.

---

## 2. Mock Data & Hardcoded Values Inventory

### 2.1. Dedicated Mock Data File (`frontend/src/services/mockData.ts`)
The file `frontend/src/services/mockData.ts` is **598 lines (23.8 KB)** of 100% fabricated, static sample data:

| Constant | Line Range | Description / Contents |
| :--- | :--- | :--- |
| `mockRequisitions` | Lines 11–189 | 6 hardcoded job postings (`req-ah-2049`, `req-ah-2060`, `req-ah-2051`, `req-ah-2055`, `req-ah-2058`, `req-ah-2062`) with simulated hiring leads, static Google usercontent avatar URLs, pipeline numbers, and salary bands. |
| `mockCandidates` | Lines 190–481 | 5 complete mock candidate dossiers (`Dr. Elena Rostova`, `Marcus Thorne`, `Maya Lin`, `Alex Chen`, `Sarah Chen-Williams`). Contains completely fabricated GitHub code repo metrics (1,420 commits/yr, 4.8k stars, 0.02 architecture smell), fake ATS compensation bands, fake The Work Number API employment histories, and fake contact info. |
| `mockChatDialogue` | Lines 482–503 | Fabricated back-and-forth chat history between recruiter "Sarah Jenkins" and "Hive Neural Matcher". |
| `mockFunnelStages` | Lines 504–512 | Static 6-stage hiring funnel (Sourced: 1,280, AI Filtered: 624, First Round: 248, Tech Loop: 94, Exec Review: 28, Offer: 12). |
| `mockDepartmentQualities` | Lines 513–551 | Hardcoded P50/P75/P90 percentile scores across 4 departments (Engineering, Product, Sales, Data). |
| `mockSourcingChannels` | Lines 552–558 | Static channel breakdown (Direct: 42%, AI Auto Inbound: 31%, Referrals: 18%, Exec Search: 9%). |
| `mockQueryLogs` | Lines 559–598 | 4 hardcoded recruiter queries with static accuracy percentages, latency, and token metrics. |

---

### 2.2. Service Layer & API Adapters (`frontend/src/services/api.ts`)
Despite integrating with the backend, `api.ts` maintains numerous synthetic fallbacks and fabricated data transformations:

#### A. Direct Mock Imports & Artificial Delays
* **Lines 2–9:** Imports `mockRequisitions`, `mockCandidates`, `mockFunnelStages`, `mockDepartmentQualities`, `mockSourcingChannels`, `mockQueryLogs` directly from `mockData.ts`.
* **Line 37:** `const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));` — used to simulate network latency for mock fallbacks.

#### B. Fallback in `useRequisitions` (Lines 346–366)
* If the backend `/positions` endpoint throws an error or returns an empty array, the hook catches the exception and returns `mockRequisitions` with a fake 120ms delay:
  ```typescript
  // Lines 346-347
  await delay(120);
  let list = [...mockRequisitions];
  ```
  *Issue:* Masks backend connectivity issues or empty database states, displaying stale demo roles instead of informing the user.

#### C. Fabricated Data in `mapBackendCandidateToCandidate` (Lines 226–306)
When actual backend candidate briefs are retrieved from `GET /positions/{id}/candidates`, the transformer fabricates fields not present in the backend database:
* **Line 231:** `const avatarUrl = AVATAR_URLS[Math.abs(brief.id) % AVATAR_URLS.length];` — hardcoded Unsplash profile photos.
* **Line 233:** `const fitScore = Math.min(99, Math.max(72, Math.round(82 + experienceYears * 2)));` — synthetic formula rather than model score.
* **Line 241:** `currentCompany: 'Verified Enterprise'` — hardcoded static employer name.
* **Line 242:** `education: brief.career_level ? \`${brief.career_level} Engineer\` : 'BSc Computer Science'` — fabricated college degree.
* **Line 246:** `expectedSalary: '$190k - $220k'` — hardcoded compensation demand.
* **Line 247:** `noticePeriod: '2 weeks'` — hardcoded availability.
* **Line 248:** `location: brief.location || 'San Francisco, CA'` — static city fallback.
* **Line 249:** `email: brief.email || \`candidate-${brief.id}@example.com\`` — dummy email address.
* **Line 250:** `phone: '+1 (415) 880-9214'` — hardcoded phone number.
* **Line 251:** `citizenship: 'US Authorized'` — hardcoded immigration status.
* **Lines 252–253:** `linkedinUrl: 'https://linkedin.com'`, `githubUrl: 'https://github.com'`.
* **Lines 269–281 (`codeRepo`):** 940 commits/yr, 32 repos, +24% QoQ velocity, 94.2% test coverage, 0 critical vulnerabilities.
* **Lines 294–303 (`atsMetadata`):** `$190k - $230k` band, 'In Budget', 'Verified Clear', 'Tier 1 Clear'.

#### D. Fallback in `useCandidate` (Lines 530–532)
* If `GET /cvs/{id}` fails or returns no document, the hook falls back to:
  ```typescript
  await delay(80);
  const found = mockCandidates.find((c) => c.id === id);
  return found || mockCandidates[0];
  ```
  *Issue:* Any non-existent candidate ID defaults to Dr. Elena Rostova.

#### E. Mock Mutation in `useAdvanceCandidateStage` (Lines 598–621)
* This mutation **never calls any backend endpoint**. It mutates the in-memory `mockCandidates` array after a fake 250ms delay:
  ```typescript
  const cand = mockCandidates.find((c) => c.id === candidateId);
  if (cand) {
    cand.status = newStage;
  }
  ```

#### F. 100% Mock Hook `useAnalytics` (Lines 623–645)
* This hook does not communicate with FastAPI at all:
  * Hardcoded KPIs: Total pipeline: 1,280 (+14.2%), Avg time to fill: 18.4 days (-4.2d), Screening accuracy: 96.2% (987 evals), Offer acceptance: 91.8% (11 of 12).
  * Returns `mockFunnelStages`, `mockDepartmentQualities`, `mockSourcingChannels`, and `mockQueryLogs`.

---

### 2.3. View & Component Layer Hardcoded Data

#### `frontend/src/components/dossier/DossierView.tsx`
* **Line 4 & Line 98:** Directly imports `mockCandidates` and displays `{mockCandidates.slice(0, 4).map((cand) => ...)}` in the left Applicant Pool rail. Real candidates from the active requisition are completely ignored in this list!
* **Line 14:** Hardcoded manager feedback fallback: `'Exceptional technical depth; demonstrated RAG systems excellence.'`
* **Line 45:** Hardcoded recruiter note author: `Sarah Jenkins (Just now): ...`
* **Line 157:** Marketing copy: *"Applicant matches are cross-referenced across 42 distinct architectural, systems latency..."*
* **Line 162:** `Cosine Fit: {telemetry?.cosineFit || 0.984}` — hardcoded 0.984 default fit.
* **Line 201:** `Lead AI Engineer Candidate • {candidate.currentCompany}` — hardcoded candidate role.
* **Lines 251, 267, 274:** Browser `alert()` calls for "Schedule Technical Loop", "Export PDF", and "Reject Candidate".
* **Line 295:** `Hash: {telemetry?.telemetryHash || '0x9b4a11c882e'}`.
* **Line 334:** Static text `"Calibrated N=1,420"`.
* **Lines 372–420:** Hardcoded fallback values: `github:erostova`, 1,420 commits across 8 repos, 4.8k stars, 0.02 architecture smell ratio.
* **Lines 434, 491, 499:** Hardcoded third-party badges: `"Verified via The Work Number API"`, `"Greenhouse Integration #GH-77821"`, `"GREENHOUSE API"`.
* **Line 517:** Hardcoded salary band fallback: `"$205,000 - $225,000 Base"`.
* **Line 532:** Hardcoded clearance fallback: `"Tier 1 Clean Clearance"`.

#### `frontend/src/components/layout/Header.tsx`
* **Line 40:** Visual shortcut tag `(Press ⌘K)`, but no keyboard event listener exists.
* **Line 55:** Static badge: `"Pipeline Live: 98.4% Match Index"`.
* **Lines 60–67:** Notifications bell has an unread red dot, but clicking it has no handler or menu.
* **Lines 75–85:** Current logged-in user is hardcoded: `"Sarah Jenkins"`, `"VP Talent Acquisition"`, with static Google avatar image.

#### `frontend/src/components/layout/Sidebar.tsx`
* **Line 16:** Hardcoded badge `'18'` on the "Job Postings" navigation item.
* **Line 83:** Hardcoded active cluster footer: `"US-EAST-AI-01"`.

#### `frontend/src/components/jobPostings/JobPostingsView.tsx` & `DepartmentTabs.tsx`
* **`DepartmentTabs.tsx` (Lines 13–15):** The department list was collapsed into a single static item:
  ```typescript
  const departments: { id: Department; label: string }[] = [
    { id: 'All Departments', label: 'All Departments' },
  ];
  ```
  The tab bar no longer filters by department because other departments were deleted.
* **`JobPostingsView.tsx` Lines 44 & 168:** Static marketing counters: `"Sync Active: 14 Nodes"`, `"Synchronizing telemetry across 14 clusters..."`.
* **`JobPostingsView.tsx` Line 156:** Static sort badge `"AI Fit Index (High-Low)"` has no dropdown menu or sort action.

#### `frontend/src/components/candidatePool/CandidateCard.tsx`
* **Line 117:** Hardcoded tag `"+ OSS Contributor (5k stars)"` unconditionally rendered on every hero candidate card.
* **Line 124:** `alert(\`Interview screen scheduled with ${candidate.name}!\`)` — browser alert popup instead of modal or integration.

#### `frontend/src/components/candidatePool/CopilotChat.tsx`
* **Line 152:** Hardcoded `"Live v4"` pill.
* **Line 188:** Hardcoded sender name: `"Sarah Jenkins"`.
* **Lines 171–174, 301, 306:** Three buttons with icons (`tune`, `attachment`, vector threshold) are presentational shells with no click listeners.

#### `frontend/src/components/settings/SettingsView.tsx`
* **Lines 151–169:** Hardcoded ATS integrations: `Greenhouse Recruiting (#GH-77821)`, `Checkr (#CHK-8810)`, `The Work Number (#TWN-902)` with fake pulsing green dots.
* **Lines 187–215:** Hardcoded algorithmic weight sliders (35% OSS, 45% Architecture, 20% Tenure) with no adjustment controls.

---

### 2.4. Tests Coupled to Mock Data (`frontend/src/tests/` & `frontend/e2e/`)
* **`frontend/src/tests/App.test.tsx` (Line 36):**
  ```typescript
  expect(screen.getAllByText(/Dr. Elena Rostova/i)[0]).toBeInTheDocument();
  ```
  The unit test explicitly requires the mock candidate "Dr. Elena Rostova" to render.
* **`frontend/e2e/recruiter.spec.ts` (Lines 11 & 20):**
  ```typescript
  await expect(page.locator('text=Lead Full-Stack AI Engineer').first()).toBeVisible();
  await expect(page.locator('text=Dr. Elena Rostova').first()).toBeVisible();
  ```
  The end-to-end Playwright test fails if mock data is replaced with empty states or actual database positions.

---

## 3. Design & UI/UX Improvement Opportunities

### 3.1. Theming Architecture & Light Mode Failure
* **The Root Problem:** `tailwind.config.js` hardcodes dark HEX values for all color tokens:
  ```javascript
  background: '#090d16',
  surface: '#0f131c',
  'surface-container': '#1c1f29',
  'on-surface': '#dfe2ef',
  ```
  Even though `darkMode: 'class'` is specified, removing `.dark` or adding `.light` on `<html>` does nothing because the color tokens are static values.
* **Design System Remediation:**
  1. Define semantic CSS variables in `frontend/src/index.css` for both light and dark themes:
     ```css
     :root {
       --color-background: 248 250 252; /* slate-50 */
       --color-surface: 255 255 255;
       --color-surface-container: 241 245 249; /* slate-100 */
       --color-on-surface: 15 23 42; /* slate-900 */
       --color-on-surface-variant: 100 116 139; /* slate-500 */
       --color-primary: 217 119 6; /* amber-600 */
     }
     .dark {
       --color-background: 9 13 22; /* #090d16 */
       --color-surface: 15 19 28; /* #0f131c */
       --color-surface-container: 28 31 41; /* #1c1f29 */
       --color-on-surface: 223 226 239;
       --color-on-surface-variant: 148 163 184;
       --color-primary: 245 158 11; /* amber-500 */
     }
     ```
  2. Reference the variables in `tailwind.config.js` via `rgb(var(--color-...) / <alpha-value>)`.
  3. Add a Theme Toggle switch in `Header.tsx` or `SettingsView.tsx` persisted to `localStorage`.

### 3.2. Responsive Layout & Mobile Breakpoints
* **Current Layout Defect:**
  * `Sidebar.tsx` is fixed at `w-64` (`left-0 top-16 bottom-0`).
  * `App.tsx` has `main className="pl-64 pt-16"`.
  * On viewports under 1024px (tablets and phones), 256px of the screen is occupied by the sidebar, leaving only a squished fraction for content.
* **Recommended Improvement:**
  * Implement a mobile drawer pattern:
    * Sidebar is hidden on small screens (`-translate-x-full lg:translate-x-0`).
    * Header displays a hamburger menu button on mobile (`lg:hidden`).
    * Opening the drawer displays a backdrop blur overlay (`bg-black/60`).
    * Main layout uses `lg:pl-64 pl-0`.

### 3.3. Interaction Design: Replace Browser `alert()` with Toasts & Dialogs
* The frontend uses raw browser `alert(...)` in 7 places:
  1. `DossierView.tsx:26`: Advance stage confirmation
  2. `DossierView.tsx:33`: Reprocess CV queued
  3. `DossierView.tsx:251`: Schedule technical loop
  4. `DossierView.tsx:267`: Export dossier PDF
  5. `DossierView.tsx:274`: Reject candidate
  6. `CandidatePoolView.tsx:101`: Export talent pool
  7. `CandidateCard.tsx:124`: Schedule screen
* **Recommended Solution:** Replace browser alerts with:
  * A lightweight Toast notification system (e.g. `sonner` or custom animated React Portal).
  * Accessible confirmation dialog modals for high-impact actions (Reject, Stage Advancement, Schedule Loop).

### 3.4. Deconstruct Monolithic Views into Reusable Subcomponents
* Two components are oversized and handle too many concerns:
  * `DossierView.tsx` (569 lines): Mixes candidate switching rails, SVG gauges, code repository telemetry, career history timelines, ATS logs, and internal notes.
  * `AnalyticsView.tsx` (506 lines): Mixes KPI cards, funnel progress bars, department percentiles, SVG donut calculations, and query log lists.
* **Target Refactored Structure:**
  ```
  src/components/dossier/
    ├── DossierView.tsx           (Orchestrator & layout)
    ├── ApplicantPoolRail.tsx     (Left candidate switcher)
    ├── TelemetryGauges.tsx       (Fit dials & competency bars)
    ├── CodeAuditCard.tsx         (Repository commits & test coverage)
    ├── EmploymentTimeline.tsx    (Work experience & tenure)
    └── DossierNotes.tsx          (Internal feedback & dispatches)

  src/components/analytics/
    ├── AnalyticsView.tsx         (Orchestrator & layout)
    ├── KpiSummaryGrid.tsx        (4 top summary cards)
    ├── FunnelProgression.tsx     (Conversion funnel steps)
    ├── DepartmentPercentiles.tsx (Discipline benchmarks)
    ├── SourcingDonut.tsx         (Channel attribution chart)
    └── QueryLogTable.tsx         (NL query history)
  ```

### 3.5. Functional `⌘K` Command Palette & Search
* In `Header.tsx`, the search bar has a `⌘K` badge, but pressing `⌘K` or `Ctrl+K` does nothing.
* Global search query state is tracked in `NavigationContext`, but searching in the header only partially filters requisitions in `JobPostingsView` and does not search candidates, CV text, or skills across the app.
* Add a global `keydown` listener that opens a dedicated Command Palette modal allowing quick navigation to positions, candidates, and actions.

### 3.6. Empty States & Error Boundaries
* If the backend is unreachable:
  * Currently, `App.tsx` shows `Connecting to CV Analyzer...` indefinitely if `ensureOrganization()` fails without setting `authReady`.
  * If a position has no candidates, `CandidatePoolView` shows an empty box without an immediate CTA to upload CVs.
* Provide clear, actionable empty states with a direct link: *"No candidates uploaded yet. Click here to upload CVs for this position."*

---

## 4. Prioritized Remediation Plan

| Priority | Task | Target Files | Impact |
| :---: | :--- | :--- | :--- |
| **P0** | **Sever Mock Data Fallbacks** | `api.ts`, `DossierView.tsx` | Eliminates fake fallbacks. Displays authentic backend data or clean empty states. Connects applicant pool rail to real requisition candidates. |
| **P0** | **Fix Dossier Applicant Rail** | `DossierView.tsx` | Replace `mockCandidates.slice(0, 4)` with `useCandidates(selectedRequisitionId)` so the rail shows real candidates for the current role. |
| **P1** | **Clean Up Synthetic Transformers** | `api.ts` (`mapBackendCandidateToCandidate`) | Remove hardcoded `$190k - $220k`, `'Verified Enterprise'`, and fake degrees. Default to `'Not specified'` or raw extraction attributes. |
| **P1** | **Replace `alert()` with Toasts/Modals** | `CandidateCard.tsx`, `DossierView.tsx`, `CandidatePoolView.tsx` | Professional user feedback replacing disruptive browser popups. |
| **P1** | **Responsive Sidebar & Mobile Drawer** | `Sidebar.tsx`, `Header.tsx`, `App.tsx` | Full tablet & smartphone usability. |
| **P2** | **Implement Real Theme Variables** | `index.css`, `tailwind.config.js`, `Header.tsx` | True light/dark mode support switching through CSS custom properties. |
| **P2** | **Restore Department Filter Tabs** | `DepartmentTabs.tsx`, `JobPostingsView.tsx` | Populate `Engineering`, `Product & Design`, `Sales & Marketing`, `Data & AI` tabs dynamically from positions. |
| **P2** | **Decompose Monolithic Views** | `DossierView.tsx`, `AnalyticsView.tsx` | Better maintainability, testability, and component isolation. |
| **P3** | **Decouple Tests from Mock Names** | `App.test.tsx`, `recruiter.spec.ts` | Update tests to assert on dynamic data or use MSW mocks rather than `Dr. Elena Rostova`. |

---

## 5. Conclusion

The Adobee Hive frontend has a world-class visual design foundation, but contains significant prototype artifacts (mock constants, hardcoded strings, non-functional controls, and static fallbacks). By executing the remediation roadmap above, the platform will transition from a mock-heavy prototype into a production-grade, responsive, and data-accurate recruitment intelligence application.
