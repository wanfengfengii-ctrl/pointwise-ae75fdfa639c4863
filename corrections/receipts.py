from dataclasses import dataclass, replace
import json
import sqlite3

from intake.limits import decode_integer, encode_integer
from source.database import require_record_number, source_read_transaction
from source.revisions import SlotRevision, read_revision


@dataclass(frozen=True, slots=True)
class EditReceipt:
    receipt_id: int
    sheet_number: int
    targets: tuple[tuple[str, int], ...]
    revisions: tuple[SlotRevision, ...]


def build_receipt(
    receipt_id: int,
    sheet_number: int,
    targets: tuple[tuple[str, int], ...],
    revisions: tuple[SlotRevision, ...],
) -> EditReceipt:
    linked = tuple(replace(revision, receipt_id=receipt_id) for revision in revisions)
    return EditReceipt(receipt_id, sheet_number, targets, linked)


def store_receipt(
    db: sqlite3.Connection,
    sheet_number: int,
    targets: tuple[tuple[str, int], ...],
    revisions: tuple[SlotRevision, ...],
) -> EditReceipt:
    if not db.in_transaction:
        raise ValueError('storing an edit receipt requires the slot transaction')
    payload = json.dumps([(name, encode_integer(count)) for name, count in targets],
                         ensure_ascii=False, separators=(',', ':'))
    inserted = db.execute('INSERT INTO edit_receipts (sheet_number, targets) VALUES (?, ?)',
                          (sheet_number, payload))
    receipt = build_receipt(inserted.lastrowid, sheet_number, targets, revisions)
    db.executemany('INSERT INTO receipt_slots (receipt_id, slot_id, revision) VALUES (?, ?, ?)',
                   ((receipt.receipt_id, slot.slot_id, slot.revision) for slot in receipt.revisions))
    return receipt


def read_receipt(db: sqlite3.Connection, receipt_id: int) -> EditReceipt:
    require_record_number(receipt_id, 'receipt number')
    with source_read_transaction(db):
        row = db.execute('SELECT sheet_number, targets FROM edit_receipts WHERE receipt_id = ?',
                         (receipt_id,)).fetchone()
        if row is None:
            raise KeyError(receipt_id)
        sheet_number, payload = row
        targets = tuple((name, decode_integer(count)) for name, count in json.loads(payload))
        links = db.execute('SELECT slot_id, revision FROM receipt_slots WHERE receipt_id = ? ORDER BY slot_id',
                           (receipt_id,))
        revisions = tuple(read_revision(db, slot, revision) for slot, revision in links)
        return EditReceipt(receipt_id, sheet_number, targets, revisions)
