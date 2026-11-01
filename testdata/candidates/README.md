# candidates — CV-based vaults for hiring

Eight fictional people whose folders were made from the CV analyzer's output, so there is something to
interview. They are not in `vaults/`: the 61 entities there are measured by an answer key and a size ceiling,
and these are a different corpus.

```
testdata/candidates/elena-rostova/
  about.md        name and summary, what the Card calls them
  work.md         "What I offer": headline role, recent roles, certificates (published on the Card)
  contact.md      email: ask first, phone: never
  visibility.md   cv.json: shared  (the Card never mentions it)
  agent.md        screening: yes | ask | no
  cv.json         the whole CVExtraction, contact details blanked
```

Made by `code/backend/tools/cv_to_vault.py` from `code/cv_analyzer/samples/extractions/`; a test fails if they
drift from it. Mixed on purpose: six say `screening: yes`, `lena-frei` says `ask` and `oliver-grant` says `no`.

```bash
cd code/backend
python tools/cv_to_vault.py            # rewrite from the extractions
python tools/cv_to_vault.py --check    # exit 1 if a file would change
FOLDER_ROOT=../../testdata/candidates python -m uvicorn app.main:app --env-file ../.env
python tools/seed_vaults.py --vaults ../../testdata/candidates
```

A hub whose `FOLDER_ROOT` is this folder, seeded with the line above, answers
`hr_shortlist` and `hr_interview` for `code/cv_analyzer/job_postings/*.txt`. To add a person, put a PDF résumé
through `code/cv_analyzer`, drop the JSON in `samples/extractions/` and run the tool.
