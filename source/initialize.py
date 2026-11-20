from collections.abc import Iterable
from dataclasses import dataclass
import sqlite3

from intake.origin import OriginRef
from source.revisions import append_revision
from source.slots import SlotRecord, insert_slot


class SlotAlreadyExists(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InitialSlot:
    slot_id: str
    capacity: int
    count: int
    origin: OriginRef


def initialize_batch_slots(db: sqlite3.Connection, batch_id: str, rows: Iterable[InitialSlot]) -> None:
    if not db.in_transaction:
        raise ValueError('initializing slots requires the batch transaction')
    for position, row in enumerate(rows):
        if db.execute('SELECT 1 FROM slots WHERE slot_id = ?', (row.slot_id,)).fetchone() is not None:
            raise SlotAlreadyExists(row.slot_id)
        insert_slot(db, SlotRecord(row.slot_id, batch_id, row.capacity, row.origin, 1), position)
        append_revision(db, row.slot_id, 1, row.count)
