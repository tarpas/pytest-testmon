#!/usr/bin/env python3
import sys
import os
import sqlite3
from typing import Any, Iterable

DEFAULT_DB = "/Users/andrew_yos/ezmon-test/.testmondata"

def connect_readonly(path: str) -> sqlite3.Connection:
    # Read-only connection (safer); falls back to normal open if URI fails.
    uri = f"file:{path}?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        return sqlite3.connect(path)

def format_value(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bytes):
        # Show blobs briefly
        return f"<BLOB {len(v)} bytes>"
    return str(v)

def print_section(title: str) -> None:
    print("=" * 80)
    print(title)
    print("=" * 80)

def print_sub(title: str) -> None:
    print(f"-- {title}")

def list_user_tables(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT name, sql
        FROM sqlite_schema
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name COLLATE NOCASE;
    """)
    return [(r[0], r[1]) for r in cur.fetchall()]

def get_table_info(conn: sqlite3.Connection, table: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info("{table}")')
    cols = []
    for cid, name, ctype, notnull, dflt_value, pk in cur.fetchall():
        cols.append({
            "cid": cid,
            "name": name,
            "type": ctype or "",
            "notnull": bool(notnull),
            "default": dflt_value,
            "pk": bool(pk),
        })
    return cols

def get_foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(f'PRAGMA foreign_key_list("{table}")')
    fks = []
    for (id_, seq, ref_table, from_col, to_col, on_update, on_delete, match) in cur.fetchall():
        fks.append({
            "ref_table": ref_table,
            "from": from_col,
            "to": to_col,
            "on_update": on_update,
            "on_delete": on_delete,
            "match": match,
        })
    return fks

def get_indexes(conn: sqlite3.Connection, table: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(f'PRAGMA index_list("{table}")')
    idxs = []
    for (seq, name, unique, origin, partial) in cur.fetchall():
        # fetch index columns
        ic = conn.cursor()
        ic.execute(f'PRAGMA index_info("{name}")')
        cols = [row[2] for row in ic.fetchall()]
        # fetch index SQL (may be NULL for implicit indexes)
        isql = conn.cursor()
        isql.execute("""
            SELECT sql FROM sqlite_schema
             WHERE type='index' AND name = ?
        """, (name,))
        sql_row = isql.fetchone()
        idxs.append({
            "name": name,
            "unique": bool(unique),
            "origin": origin,   # c (CREATE INDEX), u (UNIQUE), pk, etc.
            "partial": bool(partial),
            "columns": cols,
            "sql": sql_row[0] if sql_row else None
        })
    return idxs

def get_row_count(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
    return int(cur.fetchone()[0])

def stream_table_data(conn: sqlite3.Connection, table: str) -> tuple[list[str], Iterable[tuple]]:
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM "{table}"')
    colnames = [d[0] for d in cur.description]
    # Return an iterator over rows to avoid loading all into memory
    def row_iter():
        for row in cur:
            yield row
    return colnames, row_iter()

def print_columns(cols: list[dict]) -> None:
    print_sub("Columns")
    for c in cols:
        flags = []
        if c["pk"]:
            flags.append("PK")
        if c["notnull"]:
            flags.append("NOT NULL")
        flag_str = f" [{' '.join(flags)}]" if flags else ""
        default_str = f" DEFAULT {c['default']}" if c['default'] is not None else ""
        print(f"  - {c['name']} {c['type']}{flag_str}{default_str}")
    print()

def print_foreign_keys(fks: list[dict]) -> None:
    print_sub("Foreign Keys")
    if not fks:
        print("  (none)")
    else:
        for fk in fks:
            print(f"  - {fk['from']} -> {fk['ref_table']}({fk['to']})"
                  f" ON UPDATE {fk['on_update']} ON DELETE {fk['on_delete']}"
                  + (f" MATCH {fk['match']}" if fk['match'] else ""))
    print()

def print_indexes(idxs: list[dict]) -> None:
    print_sub("Indexes")
    if not idxs:
        print("  (none)")
    else:
        for idx in idxs:
            uniq = " UNIQUE" if idx["unique"] else ""
            cols = ", ".join(idx["columns"])
            print(f"  -{uniq} {idx['name']} ({cols}) origin={idx['origin']} partial={idx['partial']}")
            if idx["sql"]:
                print(f"    SQL: {idx['sql']}")
    print()

def print_table_data(table: str, colnames: list[str], rows: Iterable[tuple]) -> None:
    print_sub("Data")
    header = " | ".join(colnames)
    print(header)
    print("-" * len(header))
    for row in rows:
        print(" | ".join(format_value(v) for v in row))
    print()

def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB

    if not os.path.exists(db_path):
        print(f"ERROR: Database file not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = connect_readonly(db_path)
    conn.row_factory = None  # default tuples

    try:
        print_section(f"SQLite Database Report: {db_path}")
        # Basic pragmas (optional)
        cur = conn.cursor()
        cur.execute("PRAGMA database_list;")
        dblist = cur.fetchall()
        print_sub("Attached Databases")
        for (_, name, file) in dblist:
            print(f"  - {name}: {file}")
        print()

        tables = list_user_tables(conn)
        print_sub("Tables")
        if not tables:
            print("  (no user tables found)")
            print()
        else:
            for name, sql in tables:
                rows = get_row_count(conn, name)
                print_section(f'Table: {name}  (rows: {rows})')
                print_sub("CREATE Statement")
                print(sql or "(no SQL available)")
                print()

                cols = get_table_info(conn, name)
                print_columns(cols)

                fks = get_foreign_keys(conn, name)
                print_foreign_keys(fks)

                idxs = get_indexes(conn, name)
                print_indexes(idxs)

                # Data dump
                colnames, row_iter = stream_table_data(conn, name)
                print_table_data(name, colnames, row_iter)

        print_section("End of Report")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
