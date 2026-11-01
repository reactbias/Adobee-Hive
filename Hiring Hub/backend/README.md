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

When an organization is created through `POST /admin/organizations`, the text files in
`job_postings/` are imported as positions automatically. To import them for an existing
organization, use `POST /admin/organizations/{id}/import-job-postings` with the
`x-admin-token` header.

## Recruiter filter agent
The frontend keeps the list of candidate ids in play and sends it back with every request; the agent
only narrows it. Reset = call without ids / `filter/reset`. See `cv_analyzer/recruiter_agent.py`.

## Tests (manual, call the LLM)
`python test_one.py sample_cvs/<file>.pdf` and `python test_recruiter.py`.
