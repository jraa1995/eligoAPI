from app.db import get_size_standard as db_get

# Fallback minimal table for initial run
SIZE_TABLE = {
    "541511": {"basis": "receipts", "threshold": 34500000, "unit": "USD", "fy": 2025, "title": "Custom Computer Programming Services"},
    "541512": {"basis": "receipts", "threshold": 34500000, "unit": "USD", "fy": 2025, "title": "Computer Systems Design Services"},
    "336611": {"basis": "employees", "threshold": 1300, "unit": "employees", "fy": 2025, "title": "Ship Building and Repairing"},
}

def size_standard(naics: str):
    row = db_get(naics)
    if row:
        return {"basis": row["basis"], "threshold": row["threshold"], "unit": row["unit"], "fy": row["effective_fy"], "title": row.get("title")}
    return SIZE_TABLE.get(naics)

def compute_size_status(naics: str, basis_kind: str | None, value: float | None):
    info = size_standard(naics)
    if not info:
        return {"status": "unknown", "basis": "unknown", "threshold": None, "unit": None, "naics": naics}
    if not basis_kind or value is None or basis_kind != info["basis"]:
        return {"status": "unknown", "basis": basis_kind or "unknown", "threshold": info["threshold"], "unit": info["unit"], "naics": naics}
    status = "small" if value <= info["threshold"] else "other_than_small"
    return {"status": status, "basis": basis_kind, "threshold": info["threshold"], "unit": info["unit"], "naics": naics}
