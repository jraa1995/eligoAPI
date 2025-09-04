import csv, io
from app.db import upsert_size_standard

def import_size_csv(csv_bytes: bytes) -> int:
    f = io.StringIO(csv_bytes.decode('utf-8'))
    reader = csv.DictReader(f)
    count = 0
    for row in reader:
        # expected headers: naics,title,basis,threshold,unit,effective_fy
        rec = {
            "naics": row["naics"].strip(),
            "title": row.get("title"),
            "basis": row["basis"].strip(),
            "threshold": float(row["threshold"]),
            "unit": row["unit"].strip(),
            "effective_fy": int(row["effective_fy"])
        }
        upsert_size_standard(rec)
        count += 1
    return count
