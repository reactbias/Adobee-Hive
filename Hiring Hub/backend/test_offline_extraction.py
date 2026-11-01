"""The offline CV extraction reads the candidate, not the page marker. Run: python test_offline_extraction.py"""

from cv_analyzer import config, extractor
from cv_analyzer.documents import LoadedDocument


def test_offline_name_skips_the_page_marker():
    """documents.py starts every PDF's text with a page marker."""
    config.OPENAI_API_KEY = ""
    doc = LoadedDocument(images=[], text="--- Page 1 ---\nLena Frei - Backend Engineer\nPython and SQL")
    data = extractor.extract_cv(doc).data
    assert data.contact.full_name == "Lena Frei"
    assert data.technical_skills == ["Python", "SQL"]
    assert "Page 1" not in (data.professional_summary or "")


if __name__ == "__main__":
    test_offline_name_skips_the_page_marker()
    print("ok")
