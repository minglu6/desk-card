import sqlite3, os
db_path = os.path.expanduser("~/.codex/state_5.sqlite")
db = sqlite3.connect(db_path)
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)
for t in tables:
    cnt = db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    cols = [c[1] for c in db.execute(f'PRAGMA table_info("{t}")')]
    print(f"\n  TABLE {t}  ({cnt} rows)  cols={cols}")
    if 0 < cnt <= 30:
        for r in db.execute(f'SELECT * FROM "{t}" LIMIT 10').fetchall():
            s = str(r)[:280]
            print(f"    {s}")
