# CV Analyzer (backend)

Reads CV PDFs/images, screens them against a job posting, extracts structured JSON with an LLM, stores
it in a database, and lets a recruiter narrow candidates with natural-language filters.

## Setup
```bash
conda env create -f environment.yml && conda activate cv-analyzer
cp .env.example .env        # then fill in OPENAI_API_KEY (and OPENAI_BASE_URL if you use a gateway)
```
Run everything from this folder: the database, storage and `.env` paths are relative to it.

## Pipeline (CLI)
```bash
python run_pipeline.py sample_cvs --fresh --position "Senior Software Engineer" \
    --description-file job_postings/senior_software_engineer.txt
```
CVs that do not fit the job description are marked `rejected` and nothing about the candidate is stored.
Each position (job) has its own CV set; results land in `output/<position>/`.

## API
```bash
uvicorn cv_analyzer.api:app --reload
```
Key endpoints (header `x-api-key`): `POST /positions`, `POST /positions/{id}/cvs`,
`GET /positions/{id}/candidates`, `POST /positions/{id}/filter` (`{request, ids}`),
`POST /positions/{id}/filter/reset`.

## Recruiter filter agent
The frontend keeps the list of candidate ids in play and sends it back with every request; the agent
only narrows it. Reset = call without ids / `filter/reset`. See `cv_analyzer/recruiter_agent.py`.

## Tests (manual, call the LLM)
`python test_one.py sample_cvs/<file>.pdf` and `python test_recruiter.py`.

## In the Hive

This folder is the *ingest* side of hiring on the Hive. It turns a PDF résumé into a `CVExtraction` (JSON); the
Hive reads that JSON from a person's folder:

```
CV PDF ──run_pipeline.py──▶ samples/extractions/<name>.json
        ──code/backend/tools/cv_to_vault.py──▶ testdata/candidates/<name>/  (about, work, agent.md, cv.json)
        ──tools/seed_vaults.py──▶ a person Card on a hub
        ──hr_shortlist / hr_interview──▶ ranked by what their agent says from cv.json
```

The Hive backend does not import this package and needs none of its dependencies (`openai`, `pymupdf`,
`sqlalchemy`): `app/interview.py` only reads the JSON. Run this part in its own conda environment
(`environment.yml`), as above. `samples/extractions/` holds the eight sample outputs, so the Hive side can be tried
without a key; `job_postings/*.txt` are postings both sides understand. How to run the Hive side and what to try:
[documentation/HIRING.md](../../documentation/HIRING.md).

`recruiter_agent.py` here is the model-driven recruiter filter over a SQL database of candidates. The Hive's
counterpart is `app/talent.py` (rules, over signed cards) and `app/interview.py` (agents, over folders); the idea
they share is that the model, when there is one, only widens the search terms and the matching is deterministic.