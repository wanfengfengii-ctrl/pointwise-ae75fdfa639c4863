from dataclasses import dataclass
import sqlite3

from intake.limits import decode_integer, encode_integer
from source.database import require_record_number


@dataclass(frozen=True, slots=True)
class SlotRevision:
    slot_id: str
    revision: int
    count: int
    receipt_id: int | None = None


def append_revision(db: sqlite3.Connection, slot_id: str, revision: int, count: int) -> SlotRevision:
    if not db.in_transaction:
        raise ValueError('appending a revision requires a transaction')
    require_record_number(revision, 'revision')
    db.execute('INSERT INTO slot_revisions (slot_id, revision, pulse_count) VALUES (?, ?, ?)',
               (slot_id, revision, encode_integer(count)))
    return SlotRevision(slot_id, revision, count)


def read_revision(db: sqlite3.Connection, slot_id: str, revision: int) -> SlotRevision:
    require_record_number(revision, 'revision')
    row = db.execute(
        '''SELECT r.pulse_count, linked.receipt_id
             FROM slot_revisions AS r
             LEFT JOIN receipt_slots AS linked
               ON r.slot_id = linked.slot_id AND r.revision = linked.revision
            WHERE r.slot_id = ? AND r.revision = ?''',
        (slot_id, revision),
    ).fetchone()
    if row is None:
        raise KeyError((slot_id, revision))
    count, receipt_id = row
    return SlotRevision(slot_id, revision, decode_integer(count), receipt_id)
