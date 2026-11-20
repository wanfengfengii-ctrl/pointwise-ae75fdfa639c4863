from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3


_SOURCE_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS batches (
           batch_id TEXT PRIMARY KEY NOT NULL
       )''',
    '''CREATE TABLE IF NOT EXISTS slots (
           slot_id TEXT PRIMARY KEY NOT NULL,
           batch_id TEXT NOT NULL REFERENCES batches(batch_id),
           position INTEGER NOT NULL,
           capacity TEXT NOT NULL,
           export_id TEXT NOT NULL,
           line_number TEXT NOT NULL,
           current_revision INTEGER NOT NULL CHECK (current_revision > 0),
           UNIQUE (batch_id, position),
           FOREIGN KEY (slot_id, current_revision) REFERENCES slot_revisions(slot_id, revision)
               DEFERRABLE INITIALLY DEFERRED
       )''',
    '''CREATE TABLE IF NOT EXISTS slot_revisions (
           slot_id TEXT NOT NULL REFERENCES slots(slot_id),
           revision INTEGER NOT NULL CHECK (revision > 0),
           pulse_count TEXT NOT NULL,
           PRIMARY KEY (slot_id, revision)
       )''',
    '''CREATE TABLE IF NOT EXISTS edit_receipts (
           receipt_id INTEGER PRIMARY KEY,
           sheet_number INTEGER NOT NULL CHECK (sheet_number > 0),
           targets TEXT NOT NULL
       )''',
    '''CREATE TABLE IF NOT EXISTS receipt_slots (
           receipt_id INTEGER NOT NULL REFERENCES edit_receipts(receipt_id),
           slot_id TEXT NOT NULL,
           revision INTEGER NOT NULL,
           PRIMARY KEY (receipt_id, slot_id),
           UNIQUE (slot_id, revision),
           FOREIGN KEY (slot_id, revision) REFERENCES slot_revisions(slot_id, revision)
       )''',
)


def require_record_number(value: object, field: str) -> int:
    if type(value) is not int or not 1 <= value <= (1 << 63) - 1:
        raise ValueError(f'{field} must be a positive SQLite integer')
    return value


@contextmanager
def _transaction(db: sqlite3.Connection, begin: str) -> Iterator[sqlite3.Connection]:
    if db.in_transaction:
        raise ValueError('operation requires a connection without an active transaction')
    db.execute(begin)
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise


def source_read_transaction(db: sqlite3.Connection):
    return _transaction(db, 'BEGIN')


def source_write_transaction(db: sqlite3.Connection):
    return _transaction(db, 'BEGIN IMMEDIATE')


def initialize_source_schema(db: sqlite3.Connection) -> None:
    with source_write_transaction(db):
        for statement in _SOURCE_SCHEMA:
            db.execute(statement)


def open_database(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('PRAGMA journal_mode = WAL').fetchone()
    except BaseException:
        db.close()
        raise
    return db


def open_source_database(path: str | Path) -> sqlite3.Connection:
    db = open_database(path)
    try:
        initialize_source_schema(db)
    except BaseException:
        db.close()
        raise
    return db
