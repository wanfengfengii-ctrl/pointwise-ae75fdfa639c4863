from collections.abc import Callable, Iterable
from dataclasses import dataclass
import sqlite3
from typing import TypeVar

from intake.limits import validate_pulse_count
from source.database import source_write_transaction
from source.revisions import SlotRevision, append_revision, read_revision
from source.slots import get_slot_record, set_current_revision


class StaleRevision(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExpectedSlotRevision:
    slot_id: str
    revision: int
    issued_count: int
    capacity: int
    new_count: int


_Result = TypeVar('_Result')


def commit_revisions(
    db: sqlite3.Connection,
    batch_id: str,
    changes: Iterable[ExpectedSlotRevision],
    stage_result: Callable[[sqlite3.Connection, tuple[SlotRevision, ...]], _Result],
) -> _Result:
    ordered = tuple(sorted(changes, key=lambda change: change.slot_id))
    if not ordered or len({change.slot_id for change in ordered}) != len(ordered):
        raise ValueError('expected a nonempty group with distinct slots')
    with source_write_transaction(db):
        for change in ordered:
            try:
                record = get_slot_record(db, change.slot_id)
            except KeyError as exc:
                raise StaleRevision(f'unknown source slot {change.slot_id!r}') from exc
            if record.batch_id != batch_id or record.current_revision != change.revision:
                raise StaleRevision(f'source revision changed for {change.slot_id!r}')
            current = read_revision(db, change.slot_id, record.current_revision)
            if current.count != change.issued_count or record.capacity != change.capacity:
                raise StaleRevision(f'source facts differ for {change.slot_id!r}')
            validate_pulse_count(change.new_count, record.capacity)
        staged = []
        for change in ordered:
            new = append_revision(db, change.slot_id, change.revision + 1, change.new_count)
            set_current_revision(db, new.slot_id, new.revision)
            staged.append(new)
        result = stage_result(db, tuple(staged))
    return result
