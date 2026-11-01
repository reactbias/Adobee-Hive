"""Usage: python test_one.py sample_cvs/cv.pdf [custom_fields.json]"""
import json
import sys
from pathlib import Path

from cv_analyzer import config
from cv_analyzer.derived import compute_derived
from cv_analyzer.documents import load_document
from cv_analyzer.extractor import extract_cv

path = Path(sys.argv[1])
custom = json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else []

doc = load_document(path, dpi=config.IMAGE_DPI, max_pages=config.MAX_PAGES)
print(f"Loaded: pages={doc.page_count} images={len(doc.images)} "
      f"text_chars={len(doc.text)} links={len(doc.links)}")

print("Calling OpenAI... (10-60 s)")
res = extract_cv(doc, custom_fields=custom)
derived = compute_derived(res.data, config.SHORT_TENURE_MONTHS, config.GAP_MONTHS)

ex = res.data
print(f"\nModel: {res.model} | prompt tokens: {res.prompt_tokens} | completion tokens: {res.completion_tokens}")
print(f"Name:        {ex.contact.full_name}")
print(f"Email/phone: {ex.contact.email} / {ex.contact.phone}")
print(f"Title:       {ex.current_job_title} ({ex.career_level})")
print(f"Experience:  LLM={ex.total_years_experience}y | computed={derived['computed_years_experience']}y")
print(f"Jobs:        {[(w.job_title, w.company, w.start_date, w.end_date) for w in ex.work_experience]}")
print(f"Education:   {[(e.degree, e.institution, e.graduation_date) for e in ex.education]}")
print(f"Tech skills: {ex.technical_skills}")
print(f"Tools:       {ex.software_and_tools}")
print(f"Extra info:  {[(a.key, a.value) for a in ex.additional_info]}")
print(f"Custom:      {[(c.field_name, c.value, c.confidence) for c in ex.custom_fields]}")
print(f"Gaps:        {derived['employment_gaps']}")
print(f"Takeaways:   {ex.key_takeaways}")

out_dir = Path("test_output")
out_dir.mkdir(exist_ok=True)
out_file = out_dir / f"{path.stem}.json"
out_file.write_text(json.dumps({"extraction": ex.model_dump(), "derived": derived,
                                "usage": {"model": res.model, "prompt_tokens": res.prompt_tokens,
                                          "completion_tokens": res.completion_tokens}},
                               indent=2, ensure_ascii=False))
print(f"\nFull JSON written to {out_file}")