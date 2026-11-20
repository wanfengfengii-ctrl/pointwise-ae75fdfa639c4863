from collections.abc import Mapping
import sqlite3

from corrections.orders import prepare_edit_order
from corrections.receipts import EditReceipt, store_receipt
from corrections.resolve import ResolutionStatus, resolve_edit
from sheets.format import FixedSheet
from source.commit import ExpectedSlotRevision, commit_revisions
from source.revisions import SlotRevision


def submit_edit(
    db: sqlite3.Connection, piece: bytes | FixedSheet, targets: Mapping[str, int],
) -> EditReceipt | ResolutionStatus:
    order = prepare_edit_order(piece, targets)
    resolution = resolve_edit(order)
    if resolution.status is not ResolutionStatus.UNIQUE:
        return resolution.status

    changes = tuple(ExpectedSlotRevision(slot.slot_id, slot.revision, slot.count, slot.capacity, count)
                    for slot, count in resolution.assignments)

    def stage_receipt(connection: sqlite3.Connection, revisions: tuple[SlotRevision, ...]) -> EditReceipt:
        return store_receipt(connection, order.sheet.sheet_number, order.targets, revisions)

    return commit_revisions(db, order.sheet.batch_id, changes, stage_receipt)
