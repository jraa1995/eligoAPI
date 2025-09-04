import sqlite3, json, time
from typing import Any, Iterable
from app.config import get_settings

settings = get_settings()

DDL = [
    """
    CREATE TABLE IF NOT EXISTS audits(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      route TEXT NOT NULL,
      payload TEXT NOT NULL,
      response TEXT NOT NULL
    );
    """ ,
    """
    CREATE TABLE IF NOT EXISTS jobs(
      id TEXT PRIMARY KEY,
      created_ts INTEGER NOT NULL,
      status TEXT NOT NULL,
      total INTEGER NOT NULL,
      done INTEGER NOT NULL DEFAULT 0,
      webhook_url TEXT,
      requester TEXT
    );
    """ ,
    """
    CREATE TABLE IF NOT EXISTS job_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      job_id TEXT NOT NULL,
      idx INTEGER NOT NULL,
      payload TEXT NOT NULL,
      status TEXT NOT NULL,
      result TEXT,
      FOREIGN KEY(job_id) REFERENCES jobs(id)
    );
    """ ,
    """
    CREATE TABLE IF NOT EXISTS size_standards(
      naics TEXT PRIMARY KEY,
      title TEXT,
      basis TEXT,
      threshold REAL,
      unit TEXT,
      effective_fy INTEGER
    );
    """
]

_conn = None

def connect():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        for stmt in DDL:
            _conn.execute(stmt)
        _conn.commit()
    return _conn

# --- Audit ---
def write_audit(route: str, payload: dict, response: dict):
    conn = connect()
    conn.execute(
        "INSERT INTO audits(ts,route,payload,response) VALUES (?,?,?,?)",
        (int(time.time()), route, json.dumps(payload), json.dumps(response)),
    )
    conn.commit()

# --- Size standards ---
def upsert_size_standard(row: dict):
    conn = connect()
    conn.execute(
        "REPLACE INTO size_standards(naics,title,basis,threshold,unit,effective_fy) VALUES (?,?,?,?,?,?)",
        (
            row.get("naics"), row.get("title"), row.get("basis"),
            row.get("threshold"), row.get("unit"), row.get("effective_fy")
        ),
    )
    conn.commit()

def get_size_standard(naics: str):
    conn = connect()
    cur = conn.execute("SELECT * FROM size_standards WHERE naics=?", (naics,))
    r = cur.fetchone()
    return dict(r) if r else None

# --- Jobs ---
def create_job(job_id: str, total: int, webhook_url: str | None, requester: str | None):
    conn = connect()
    conn.execute(
        "INSERT INTO jobs(id,created_ts,status,total,done,webhook_url,requester) VALUES (?,?,?,?,?,?,?)",
        (job_id, int(time.time()), "queued", total, 0, webhook_url, requester),
    )
    conn.commit()

def add_job_items(job_id: str, items: Iterable[dict]):
    conn = connect()
    for idx, p in enumerate(items):
        conn.execute(
            "INSERT INTO job_items(job_id,idx,payload,status) VALUES (?,?,?,?)",
            (job_id, idx, json.dumps(p), "queued"),
        )
    conn.commit()

def fetch_next_job_item():
    conn = connect()
    cur = conn.execute(
        "SELECT * FROM job_items WHERE status='queued' ORDER BY id LIMIT 1"
    )
    r = cur.fetchone()
    return dict(r) if r else None

def mark_job_item_started(item_id: int):
    conn = connect()
    conn.execute("UPDATE job_items SET status='running' WHERE id=?", (item_id,))
    conn.commit()

def mark_job_item_done(item_id: int, result: dict):
    conn = connect()
    conn.execute("UPDATE job_items SET status='done', result=? WHERE id=?", (json.dumps(result), item_id))
    conn.commit()

def update_job_progress(job_id: str):
    conn = connect()
    cur = conn.execute("SELECT COUNT(*) c FROM job_items WHERE job_id=? AND status='done'", (job_id,))
    done = cur.fetchone()["c"]
    conn.execute("UPDATE jobs SET done=?, status=CASE WHEN ?=total THEN 'complete' ELSE status END WHERE id=?", (done, done, job_id))
    conn.commit()

def get_job(job_id: str):
    conn = connect()
    cur = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
    r = cur.fetchone()
    return dict(r) if r else None

def list_job_items(job_id: str):
    conn = connect()
    cur = conn.execute("SELECT * FROM job_items WHERE job_id=? ORDER BY idx", (job_id,))
    return [dict(x) for x in cur.fetchall()]
