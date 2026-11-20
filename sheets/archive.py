from collections.abc import Callable
from pathlib import Path
import sqlite3

from rules.catalog import initialize_recipe_schema
from sheets.format import FixedSheet, encode_sheet
from source.database import open_database, require_record_number, source_write_transaction


def open_issuance_database(path: str | Path) -> sqlite3.Connection:
    db = open_database(path)
    try:
        with source_write_transaction(db):
            initialize_recipe_schema(db)
            db.execute('''CREATE TABLE IF NOT EXISTS fixed_sheets (
                              sheet_number INTEGER PRIMARY KEY,
                              piece BLOB NOT NULL
                          )''')
    except BaseException:
        db.close()
        raise
    return db


def archive_sheet(
    db: sqlite3.Connection, build: Callable[[int], FixedSheet],
) -> tuple[FixedSheet, bytes]:
    with source_write_transaction(db):
        previous = db.execute('SELECT MAX(sheet_number) FROM fixed_sheets').fetchone()[0]
        number = 1 if previous is None else previous + 1
        sheet = build(number)
        if sheet.sheet_number != number:
            raise ValueError('fixed sheet has the wrong archive number')
        piece = encode_sheet(sheet)
        db.execute('INSERT INTO fixed_sheets (sheet_number, piece) VALUES (?, ?)', (number, piece))
    return sheet, piece


def read_archived_sheet(db: sqlite3.Connection, sheet_number: int) -> bytes:
    require_record_number(sheet_number, 'sheet number')
    row = db.execute('SELECT piece FROM fixed_sheets WHERE sheet_number = ?', (sheet_number,)).fetchone()
    if row is None:
        raise KeyError(sheet_number)
    return row[0]
