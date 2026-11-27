import sqlite3
from pathlib import Path

BASE_DIR = Path(r"C:\Users\222206\Desktop\TMC-blockchain")
VALIDATORS = [
    ("validator1", BASE_DIR / "data" / "validator1" / "tmc1.db"),
    ("validator2", BASE_DIR / "data" / "validator2" / "tmc2.db"),
    ("validator3", BASE_DIR / "data" / "validator3" / "tmc3.db"),
    ("validator4", BASE_DIR / "data" / "validator4" / "tmc4.db"),
]

for name, db_path in VALIDATORS:
    print("\n" + "=" * 55)
    print(name)
    print("Database:", db_path)

    if not db_path.exists():
        print("DATABASE NOT FOUND")
        continue

    # Подключаемся исключительно для чтения.
    uri = db_path.as_uri() + "?mode=ro"

    try:
        with sqlite3.connect(uri, uri=True) as conn:
            print("Integrity:", conn.execute(
                "PRAGMA quick_check"
            ).fetchone()[0])

            tables = conn.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name
            """).fetchall()

            print("Tables:", [table[0] for table in tables])

            for table in ("chain_state", "accounts"):
                exists = any(t[0] == table for t in tables)

                if not exists:
                    print(f"\n{table}: NOT FOUND")
                    continue

                columns = conn.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()

                print(f"\n{table} columns:",
                      [column[1] for column in columns])

                if table == "chain_state":
                    rows = conn.execute(
                        "SELECT * FROM chain_state"
                    ).fetchall()
                    print("chain_state rows:", rows)

                elif table == "accounts":
                    count = conn.execute(
                        "SELECT COUNT(*) FROM accounts"
                    ).fetchone()[0]

                    print("Account count:", count)

                    column_names = [c[1] for c in columns]

                    if "balance_minor" in column_names:
                        total = conn.execute(
                            "SELECT COALESCE(SUM(balance_minor), 0) "
                            "FROM accounts"
                        ).fetchone()[0]
                        print("Total balance (minor units):", total)

    except Exception as error:
        print("ERROR:", error)
