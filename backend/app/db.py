"""SQLite layer: schema, connections, transactions, audit log."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS shops(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL, name_hi TEXT NOT NULL, owner_name TEXT NOT NULL,
  lat REAL NOT NULL, lng REAL NOT NULL,
  cash_limit_paise INTEGER NOT NULL DEFAULT 200000,
  sharing_opt_in INTEGER NOT NULL DEFAULT 1,
  withdrawn INTEGER NOT NULL DEFAULT 0,
  disconnected INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY,
  brand TEXT NOT NULL, name TEXT NOT NULL, name_hi TEXT NOT NULL,
  variant TEXT NOT NULL DEFAULT '', pack_size REAL NOT NULL, unit TEXT NOT NULL,
  category TEXT NOT NULL, mrp_paise INTEGER NOT NULL, emoji TEXT NOT NULL DEFAULT '📦'
);

CREATE TABLE IF NOT EXISTS aliases(
  id INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  alias_text TEXT NOT NULL COLLATE NOCASE,
  lang TEXT NOT NULL DEFAULT 'en'
);
CREATE INDEX IF NOT EXISTS ix_aliases_text ON aliases(alias_text);

CREATE TABLE IF NOT EXISTS stock_lots(
  id INTEGER PRIMARY KEY,
  shop_id INTEGER NOT NULL REFERENCES shops(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  qty INTEGER NOT NULL,
  cost_paise INTEGER NOT NULL,
  expiry_date TEXT,
  condition TEXT NOT NULL DEFAULT 'sealed',
  permit_share INTEGER NOT NULL DEFAULT 1,
  slow INTEGER NOT NULL DEFAULT 0,
  retained_floor INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lots_shop ON stock_lots(shop_id);

CREATE TABLE IF NOT EXISTS needs(
  id INTEGER PRIMARY KEY,
  shop_id INTEGER NOT NULL REFERENCES shops(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  qty INTEGER NOT NULL,
  urgency TEXT NOT NULL DEFAULT 'normal',
  alt_product_ids TEXT NOT NULL DEFAULT '[]',
  budget_paise INTEGER,
  min_shelf_days INTEGER NOT NULL DEFAULT 14,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_needs_shop ON needs(shop_id);

CREATE TABLE IF NOT EXISTS supplier_quotes(
  id INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  supplier_name TEXT NOT NULL,
  price_paise INTEGER NOT NULL,
  min_order_packs INTEGER NOT NULL DEFAULT 1,
  lead_days INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS captures(
  id INTEGER PRIMARY KEY,
  shop_id INTEGER NOT NULL,
  modality TEXT NOT NULL,
  raw_text TEXT NOT NULL,
  extracted TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS planning_runs(
  id INTEGER PRIMARY KEY,
  case_id TEXT NOT NULL,
  status TEXT NOT NULL,
  params TEXT NOT NULL,
  result TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS plans(
  id INTEGER PRIMARY KEY,
  case_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  run_id INTEGER,
  supersedes_id INTEGER,
  status TEXT NOT NULL,
  proposal TEXT NOT NULL,
  inputs_hash TEXT NOT NULL,
  participants TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reservations(
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  lot_id INTEGER NOT NULL REFERENCES stock_lots(id),
  qty INTEGER NOT NULL,
  expires_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_res_plan ON reservations(plan_id);

CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  shop_id INTEGER NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT,
  decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sandbox_actions(
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  result TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sandbox_state(
  id INTEGER PRIMARY KEY CHECK(id=1),
  injections TEXT NOT NULL DEFAULT '[]'
);
INSERT OR IGNORE INTO sandbox_state(id, injections) VALUES (1, '[]');

CREATE TABLE IF NOT EXISTS audit_events(
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  event_type TEXT NOT NULL,
  ref_type TEXT,
  ref_id INTEGER,
  payload TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS idempotency(
  key TEXT PRIMARY KEY,
  response TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY,
  role TEXT NOT NULL,
  shop_id INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_log(
  id INTEGER PRIMARY KEY,
  shop_id INTEGER NOT NULL,
  lot_id INTEGER,
  product_id INTEGER NOT NULL,
  delta INTEGER NOT NULL,
  reason TEXT NOT NULL,
  actor TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  ts TEXT NOT NULL
);
"""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def connect(db_path=None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI may run dependency setup and teardown in
    # different threadpool threads; each request still owns its connection exclusively.
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db(db_path=None) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


@contextmanager
def tx(conn: sqlite3.Connection):
    """Immediate (write-locked) transaction: the atomicity unit for reservations."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def log_event(conn: sqlite3.Connection, actor: str, event_type: str,
              ref_type: str | None = None, ref_id: int | None = None,
              payload: dict | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO audit_events(ts, actor, event_type, ref_type, ref_id, payload) VALUES (?,?,?,?,?,?)",
        (now_iso(), actor, event_type, ref_type, ref_id, json.dumps(payload or {}, default=str)),
    )
    return cur.lastrowid


def jload(text, default):
    try:
        return json.loads(text) if text else default
    except (TypeError, json.JSONDecodeError):
        return default
