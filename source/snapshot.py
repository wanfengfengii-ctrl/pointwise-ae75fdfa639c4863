from collections.abc import Iterable
from dataclasses import dataclass
import sqlite3

from intake.origin import require_name
from source.database import source_read_transaction
from source.revisions import read_revision
from source.slots import get_slot_record


@dataclass(frozen=True, slots=True)
class SlotSnapshot:
    slot_id: str
    revision: int
    count: int
    capacity: int


@dataclass(frozen=True, slots=True)
class BatchSnapshot:
    batch_id: str
    slots: tuple[SlotSnapshot, ...]


def capture_snapshot(db: sqlite3.Connection, batch_id: str, slot_ids: Iterable[str]) -> BatchSnapshot:
    batch_id = require_name(batch_id, 'batch')
    requested = tuple(dict.fromkeys(require_name(slot, 'slot reference') for slot in slot_ids))
    slots = []
    with source_read_transaction(db):
        if db.execute('SELECT 1 FROM batches WHERE batch_id = ?', (batch_id,)).fetchone() is None:
            raise KeyError(batch_id)
        for slot_id in requested:
            record = get_slot_record(db, slot_id)
            if record.batch_id != batch_id:
                raise ValueError(f'slot {slot_id!r} is outside batch {batch_id!r}')
            revision = read_revision(db, slot_id, record.current_revision)
            slots.append(SlotSnapshot(slot_id, revision.revision, revision.count, record.capacity))
    return BatchSnapshot(batch_id, tuple(slots))
