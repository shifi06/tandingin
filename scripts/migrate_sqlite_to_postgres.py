#!/usr/bin/env python3
"""Copy an existing Tanding.in SQLite database into an already-migrated PostgreSQL DB.

Usage:
  DATABASE_URL='postgresql://...' python scripts/migrate_sqlite_to_postgres.py instance/tandingin.db

The destination must be empty and its schema must already exist (`flask db upgrade`).
The script preserves primary keys and fails rather than merging into non-empty tables.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import MetaData, create_engine, select, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

TABLES_IN_ORDER = [
    "roles",
    "users",
    "tim_esports",
    "turnamen",
    "pendaftaran_turnamen",
    "jadwal_match",
    "hasil_match",
]
PRIMARY_KEYS = {
    "roles": "id_role",
    "users": "id_user",
    "tim_esports": "id_tim",
    "turnamen": "id_turnamen",
    "pendaftaran_turnamen": "id_pendaftaran",
    "jadwal_match": "id_jadwal",
    "hasil_match": "id_hasil",
}


def migrate_legacy_upload(value, legacy_dir, uploaded_refs):
    """Convert old `/uploads/<name>` references to private Blob objects."""
    if not value:
        return value
    if value.startswith("/uploads/"):
        filename = Path(value).name
    elif value.startswith("local://"):
        filename = value.removeprefix("local://")
        if Path(filename).name != filename:
            raise RuntimeError("Legacy storage reference is unsafe.")
    else:
        return value
    if not legacy_dir:
        raise RuntimeError(
            "Legacy upload references exist. Pass --legacy-upload-dir pointing to instance/uploads."
        )

    from storage import VercelPrivateBlobStorage

    source_root = Path(legacy_dir).expanduser().resolve()
    source_file = (source_root / filename).resolve()
    if source_file.parent != source_root or not source_file.is_file():
        raise RuntimeError(f"Legacy upload file is missing or unsafe: {filename}")

    extension = source_file.suffix.lower()
    allowed = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    if extension not in allowed:
        raise RuntimeError(f"Unsupported legacy image extension: {filename}")
    content_type = allowed[extension]
    content = source_file.read_bytes()
    if len(content) > 4 * 1024 * 1024:
        raise RuntimeError(f"Legacy image exceeds the 4 MB application limit: {filename}")
    signatures = {
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
    }
    if not signatures[extension]:
        raise RuntimeError(f"Legacy image signature does not match its extension: {filename}")
    result = VercelPrivateBlobStorage().put(
        content, filename=filename, content_type=content_type,
        prefix="legacy-migrated",
    )
    uploaded_refs.append(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_sqlite", help="Path to the existing SQLite .db file")
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--legacy-upload-dir", help="Folder holding legacy /uploads files, e.g. instance/uploads")
    args = parser.parse_args()

    source_path = Path(args.source_sqlite).expanduser().resolve()
    target_url = (os.environ.get("MIGRATION_DATABASE_URL")
                  or os.environ.get("DATABASE_URL_UNPOOLED")
                  or os.environ.get("DATABASE_URL", ""))
    if target_url.startswith("postgres://"):
        target_url = "postgresql+psycopg://" + target_url[len("postgres://"):]
    elif target_url.startswith("postgresql://"):
        target_url = "postgresql+psycopg://" + target_url[len("postgresql://"):]
    if not source_path.is_file():
        parser.error(f"SQLite source file not found: {source_path}")
    if not target_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        parser.error("DATABASE_URL must point to PostgreSQL.")
    if args.batch_size < 1:
        parser.error("--batch-size must be greater than zero.")

    source_engine = create_engine(f"sqlite:///{source_path.as_posix()}")
    target_engine = create_engine(target_url, pool_pre_ping=True)
    source_meta = MetaData()
    target_meta = MetaData()
    copied = {}
    uploaded_refs = []

    try:
        source_meta.reflect(bind=source_engine, only=TABLES_IN_ORDER)
        target_meta.reflect(bind=target_engine, only=TABLES_IN_ORDER)
        missing_source = [name for name in TABLES_IN_ORDER if name not in source_meta.tables]
        missing_target = [name for name in TABLES_IN_ORDER if name not in target_meta.tables]
        if missing_source:
            raise RuntimeError(f"Source DB is missing tables: {', '.join(missing_source)}")
        if missing_target:
            raise RuntimeError(
                f"Destination schema is incomplete: {', '.join(missing_target)}. "
                "Run `flask --app app db upgrade` first."
            )

        with target_engine.connect() as target_check:
            occupied = []
            for name in TABLES_IN_ORDER:
                table = target_meta.tables[name]
                count = target_check.execute(select(table).limit(1)).first()
                if count is not None:
                    occupied.append(name)
            if occupied:
                raise RuntimeError(
                    "Destination tables are not empty: " + ", ".join(occupied) +
                    ". Refusing to merge or overwrite existing data."
                )

        with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
            for name in TABLES_IN_ORDER:
                source_table = source_meta.tables[name]
                target_table = target_meta.tables[name]
                result = source_conn.execute(select(source_table))
                total = 0
                while True:
                    rows = result.fetchmany(args.batch_size)
                    if not rows:
                        break
                    payload = [dict(row._mapping) for row in rows]
                    if name == "tim_esports":
                        for record in payload:
                            record["logo_url"] = migrate_legacy_upload(
                                record.get("logo_url"), args.legacy_upload_dir, uploaded_refs
                            )
                    elif name == "hasil_match":
                        for record in payload:
                            record["foto_bukti_url"] = migrate_legacy_upload(
                                record.get("foto_bukti_url"), args.legacy_upload_dir, uploaded_refs
                            )
                    target_conn.execute(target_table.insert(), payload)
                    total += len(payload)
                copied[name] = total

            # Explicitly imported integer keys must advance PostgreSQL sequences.
            for table_name, column_name in PRIMARY_KEYS.items():
                target_conn.execute(
                    text(
                        "SELECT setval(pg_get_serial_sequence(:table_name, :column_name), "
                        "COALESCE(MAX(" + column_name + "), 1), "
                        "MAX(" + column_name + ") IS NOT NULL) FROM " + table_name
                    ),
                    {"table_name": table_name, "column_name": column_name},
                )

        print("SQLite → PostgreSQL migration completed:")
        for name, count in copied.items():
            print(f"  {name}: {count} rows")
        print("Primary keys preserved; PostgreSQL sequences adjusted.")
        return 0
    except Exception:
        # If the DB transaction fails after file uploads, clean up any orphaned blobs.
        if uploaded_refs:
            try:
                from storage import VercelPrivateBlobStorage
                store = VercelPrivateBlobStorage()
                for ref in uploaded_refs:
                    store.delete(ref)
            except Exception:
                print("WARNING: unable to clean up some orphaned Blob objects", file=sys.stderr)
        raise
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
