"""ShelfLoop configuration. All money is integer paise (₹1 = 100 paise)."""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
ROOT_DIR = BASE_DIR.parent                                  # shelfloop/
DATA_DIR = ROOT_DIR / "data"
DB_PATH = Path(os.environ.get("SHELFLOOP_DB_PATH", DATA_DIR / "shelfloop.db"))
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

CASE_ID = "cluster-main"

RESERVATION_TTL_S = 600            # 10-minute holds while awaiting approvals
DEFAULT_MIN_SHELF_DAYS = 14        # planning threshold at handoff, not a safety certification
DEFAULT_TIME_LIMIT_MS = 5000
DEFAULT_RADIUS_KM = 3.0

TRANSPORT_RATE_PAISE_PER_PACK_KM = 200   # ₹2 per pack-km, assumption shown on receipts
TRANSPORT_BASE_PAISE = 5000              # ₹50 call-out charge per cycle, split evenly
SLOW_REDEPLOY_BONUS_PAISE = 300          # per-pack preference for marked slow stock
COVERAGE_WEIGHT = 1_000_000              # objective weight per urgency-weighted pack
URGENCY_WEIGHTS = {"urgent": 2, "normal": 1}

OWNER_PIN = "1234"
OPERATOR_PIN = "0000"

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:4b"
OLLAMA_TIMEOUT_S = 2.0

MAX_CYCLES = 20000                  # enumeration guard
MAX_PRODUCTS_PER_PAIR = 3           # candidate products kept per ordered shop pair
