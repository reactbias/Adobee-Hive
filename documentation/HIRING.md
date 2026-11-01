# Hiring: how it works and how to test it

A company pastes a job posting. The Hive reads it into requirements, shows the people whose signed cards fit it,
and, when the recruiter chooses, the recruiter's agent interviews each person's agent. A person's agent answers
from its owner's folder, only if the owner said yes, and only from files the owner shared.

What each part is, in the order it runs:

| Step | Where | What it does |
| --- | --- | --- |
| Read the posting | `app/talent.py` `parse_job` | Splits it into must-haves, the role, nice-to-haves, years, place, languages. "AWS, Azure or GCP" is one requirement |
| Search the cards | `talent.search` | Reads each person card's `offers`, `skills`, headline, description and countersigned claims, never `needs`. Per requirement: **literal**, **related** (React implies frontend), **partial** or **similar** (`semantic.py`) |
| Ask for consent | `app/interview.py` `CandidateAgent.consent` | A person's answer on the hub, else `agent.md` in their folder, else `ask`. `yes` opens a folder link and grants the files they admitted. `ask` records a request and reads nothing. `no` is left alone |
| Interview | `interview.interview` | The recruiter's agent asks one question per requirement, plus years, availability and rates. The candidate's agent answers by **quoting lines** from the shared files and naming the file. Nothing relevant means it says so |
| Rank | `interview.run` | The posting is scored again with those lines as evidence |

Nobody is introduced. The next step is the existing introduction, which waits for the person's yes.

Three ways in: the **Hiring** screen of the app, two MCP tools (`hr_shortlist`, `hr_interview`) and REST
(`POST /api/hr/shortlist`, `/api/hr/interview`, `/api/hr/screening/{card_id}`).

## Run the real thing

You need Python 3.12 and Node 22. No Docker, no API key.

```bash
git clone … && cd Adobee-Hive/code/backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt   # Windows: .venv\Scripts\python.exe
```

**1. Start a hub with eight CV-based candidates** (one terminal, from `code/backend`):

```bash
./hiring_hub.sh            # Windows: hiring_hub.bat
```

It starts the hub on `:8000` with `ADMISSION_POLICY=open` and `FOLDER_ROOT=testdata/candidates`, then registers the
eight people from `testdata/candidates/` through the real signup endpoint. If your Python is elsewhere, set
`HIVE_PY` first. Check: `curl http://127.0.0.1:8000/api/health` answers `ok`.

**2. Start the app** (second terminal):

```bash
cd code/frontend && npm ci && npm run dev
```

Open <http://localhost:5173/#hire> (the third link in the header, **Hiring**).

## What to try, and what you should see

1. **It opens on a sample posting** and, within a second, lists people. *What the Hive understood* shows one chip
   per requirement; "cloud (AWS, Azure or GCP)" is one chip. Hover a chip to see what else counts for it.
2. **Change the posting** (pick *Marketing Manager (B2B)* from the sample list, or type). The people change:
   Hannah Fischer comes first for marketing, and none of the engineers are listed. Open *What the card says* on a
   person: each line shows how it was found (**says it**, **implies it**, **partly**, **close to it**).
3. **Nothing has been asked of anyone yet.** *Start the interviews* is the only thing that starts the agents.
4. With the software posting, press it. *Who said yes*: Elena, Tobias, Jonas and Camille **said yes** (their
   `agent.md`), Lena Frei **asked, waiting for their yes**, Oliver Grant **said no**. The yes rows list the files
   shared (`about.md`, `cv.json`, `work.md`), never the contact details.
5. **Watch the agents talk**: the recruiter's agent asks, the person's agent answers with quoted lines and the file
   they came from. *Show the whole interview* skips the pacing. Switch person with the tabs.
6. **Say yes for Lena Frei** (the button under her row). Her folder opens, the interviews run again and she is
   interviewed. The button plays the person's part; on a real hub the person says it, or writes
   `screening: yes` in their `agent.md`. If you start the hub with `OWNER_EDIT_TOKEN=…`, the page asks for it.
7. **Edit the posting after an interview**: the page says the interview is out of date. Start again for the new one.
8. Switch the language (EN, DE, FR, IT) and the dark scheme: everything on the screen follows.

Things worth trying to break: an empty posting; a posting in German; a requirement nobody has; a 5,000-line paste
(refused over 6,000 characters); stopping the hub mid-interview (the page says it can not reach the hub).

## Check it from outside the page

```bash
curl -s localhost:8000/api/hr/shortlist -H 'Content-Type: application/json' \
  -d '{"job":"Marketing Manager\n\nRequirements:\n- B2B marketing; SEO","limit":3}'

curl -s localhost:8000/api/hr/interview -H 'Content-Type: application/json' \
  -d '{"job":"Senior Software Engineer\n\nRequirements:\n- Python\n- Kubernetes","limit":5}'

curl -s localhost:8000/api/hr/screening/lena-frei -H 'Content-Type: application/json' -d '{"screening":"yes"}'
```

The interview body has no field for approval, and an `approve` key sent anyway is ignored: only the person's own
answer opens a folder. Over MCP (`/mcp/`) the same two tools are `hr_shortlist` and `hr_interview`, and neither
takes an approval argument either.

## Automated tests

```bash
cd code/backend && python -m pytest tests/test_talent.py tests/test_interview.py tests/test_hiring_api.py tests/test_docs.py -q
cd code/frontend && npm test && npm run build
```

`ruff check . && ruff format --check .` (backend) and `npm run format:check` (frontend) are what CI runs too.

## Your own people

Put a résumé PDF through `code/cv_analyzer` (needs an OpenAI key; its README has the steps), keep the JSON in
`code/cv_analyzer/samples/extractions/`, then:

```bash
python tools/cv_to_vault.py        # writes testdata/candidates/<name>/, with an agent.md for each person
```

Edit `testdata/candidates/<name>/agent.md` (`screening: yes`, `ask` or `no`) to change what a person's agent does,
and run `hiring_hub.sh` again. `cv.json` is `shared` in `visibility.md`: the card never mentions it, and only a
recruiter whose request was accepted can read it.

## For presenting

`code/backend/samples/` holds two things that are **not** the product: a terminal narration (`recruit_demo.py`)
and a one-page viewer that needs only the backend (`start_sample.bat`, or `python samples/hiring_viewer.py`).
They run the same code on a throwaway hub, so a talk does not depend on a frontend build.

## What it does not do

[LIMITS.md](LIMITS.md#hiring) is the full list. The ones a tester will meet: the agents quote lines and do not
reason, so an answer can be a loosely related line labelled *loose* or *close*; nothing has been measured against
labelled data, so there is no accuracy figure; a skills list that mentions everything scores full marks; the
recruiter's name is an unauthenticated string; the person's yes is a button and not an account; PDFs are read only
when they hold plain text; and the answer text a person's agent gives when it has nothing is in English whatever
language the page is in.
