import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None   # None -> api.openai.com
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "180"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cv_analyzer.db")
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./storage"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-me")

MAX_PAGES = int(os.getenv("MAX_PAGES", "6"))          # CVs longer than this are truncated
IMAGE_DPI = int(os.getenv("IMAGE_DPI", "150"))        # 150 is a good quality/cost tradeoff
INCLUDE_TEXT_LAYER = os.getenv("INCLUDE_TEXT_LAYER", "true").lower() == "true"
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "30000"))

# Thresholds for derived metrics
SHORT_TENURE_MONTHS = int(os.getenv("SHORT_TENURE_MONTHS", "24"))
GAP_MONTHS = int(os.getenv("GAP_MONTHS", "6"))

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
# Relevance gate: CVs scoring below this against the position description are not stored
SCREENING_ENABLED = os.getenv("SCREENING_ENABLED", "true").lower() == "true"
MIN_RELEVANCE_SCORE = int(os.getenv("MIN_RELEVANCE_SCORE", "40"))
