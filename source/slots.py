from dataclasses import dataclass
import sqlite3

from intake.limits import decode_integer, encode_integer
from intake.origin import OriginRef, origin_record, require_name
from source.database import source_read_transaction
from source.revisions import read_revision


@dataclass(frozen=True, slots=True)
class SlotRecord:
    slot_id: str
    batch_id: str
    capacity: int
    origin: OriginRef
    current_revision: int


@dataclass(frozen=True, slots=True)
class SlotView:
    slot_id: str
    batch_id: str
    capacity: int
    count: int
    origin: OriginRef
    revision: int
    receipt_id: int | None


def get_slot_record(db: sqlite3.Connection, slot_id: str) -> SlotRecord:
    row = db.execute(
        'SELECT slot_id, batch_id, capacity, export_id, line_number, current_revision '
        'FROM slots WHERE slot_id = ?',
        (slot_id,),
    ).fetchone()
    if row is None:
        raise KeyError(slot_id)
    slot, batch, capacity, export, line, revision = row
    return SlotRecord(slot, batch, decode_integer(capacity), OriginRef(export, decode_integer(line)), revision)


def read_slot(db: sqlite3.Connection, slot_id: str, revision: int | None = None) -> SlotView:
    slot_id = require_name(slot_id, 'slot')
    with source_read_transaction(db):
        record = get_slot_record(db, slot_id)
        if revision is None:
            revision = record.current_revision
        value = read_revision(db, slot_id, revision)
        return SlotView(slot_id, record.batch_id, record.capacity, value.count,
                        record.origin, value.revision, value.receipt_id)


def insert_slot(db: sqlite3.Connection, record: SlotRecord, position: int) -> None:
    if not db.in_transaction:
        raise ValueError('inserting a slot requires a transaction')
    export, line = origin_record(record.origin)
    db.execute(
        '''INSERT INTO slots (slot_id, batch_id, position, capacity, export_id, line_number, current_revision)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (record.slot_id, record.batch_id, position, encode_integer(record.capacity), export, line,
         record.current_revision),
    )


def set_current_revision(db: sqlite3.Connection, slot_id: str, revision: int) -> None:
    if not db.in_transaction:
        raise ValueError('advancing a slot requires a transaction')
    changed = db.execute('UPDATE slots SET current_revision = ? WHERE slot_id = ?', (revision, slot_id))
    if changed.rowcount != 1:
        raise KeyError(slot_id)
