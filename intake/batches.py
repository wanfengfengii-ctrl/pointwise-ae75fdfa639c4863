from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import sqlite3

from intake.limits import decode_integer
from intake.origin import OriginRef, require_name
from intake.parse import ParsedSlotRow, parse_batch
from source.database import source_read_transaction, source_write_transaction
from source.initialize import InitialSlot, SlotAlreadyExists, initialize_batch_slots


class BatchConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ImportedBatch:
    batch_id: str
    rows: tuple[ParsedSlotRow, ...]


def _original_rows(db: sqlite3.Connection, batch_id: str) -> tuple[ParsedSlotRow, ...]:
    records = db.execute(
        '''SELECT s.slot_id, s.capacity, r.pulse_count, s.export_id, s.line_number
             FROM slots AS s
             JOIN slot_revisions AS r ON r.slot_id = s.slot_id AND r.revision = 1
            WHERE s.batch_id = ? ORDER BY s.position''',
        (batch_id,),
    )
    return tuple(
        ParsedSlotRow(slot, decode_integer(capacity), decode_integer(count),
                      OriginRef(export, decode_integer(line)))
        for slot, capacity, count, export, line in records
    )


def read_original_batch(db: sqlite3.Connection, batch_id: str) -> ImportedBatch:
    batch_id = require_name(batch_id, 'batch')
    with source_read_transaction(db):
        if db.execute('SELECT 1 FROM batches WHERE batch_id = ?', (batch_id,)).fetchone() is None:
            raise KeyError(batch_id)
        return ImportedBatch(batch_id, _original_rows(db, batch_id))


def import_batch(db: sqlite3.Connection, batch_id: str, rows: Iterable[Mapping]) -> ImportedBatch:
    batch = parse_batch(batch_id, rows)
    with source_write_transaction(db):
        existing = db.execute('SELECT 1 FROM batches WHERE batch_id = ?', (batch.batch_id,)).fetchone()
        if existing is not None:
            original = _original_rows(db, batch.batch_id)
            if original != batch.rows:
                raise BatchConflict(f'batch {batch.batch_id!r} has different original rows')
            return ImportedBatch(batch.batch_id, original)
        db.execute('INSERT INTO batches (batch_id) VALUES (?)', (batch.batch_id,))
        initial = tuple(InitialSlot(row.slot_id, row.capacity, row.count, row.origin)
                        for row in batch.rows)
        try:
            initialize_batch_slots(db, batch.batch_id, initial)
        except SlotAlreadyExists as exc:
            raise BatchConflict(f'slot {exc.args[0]!r} already belongs to a batch') from exc
        return ImportedBatch(batch.batch_id, batch.rows)
