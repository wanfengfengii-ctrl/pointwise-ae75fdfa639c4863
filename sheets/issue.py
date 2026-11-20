from dataclasses import dataclass
from itertools import count
import sqlite3

from rules.binding import BoundRecipe, bind_recipe
from rules.catalog import read_recipe
from rules.totals import CellTotal, calculate_totals
from sheets.archive import archive_sheet
from sheets.basis import FrozenCell, FrozenSlot, WritebackBasis
from sheets.format import FixedSheet
from source.snapshot import capture_snapshot


@dataclass(frozen=True, slots=True)
class IssuedSheet:
    sheet: FixedSheet
    piece: bytes


def build_fixed_sheet(number: int, bound: BoundRecipe, displays: tuple[CellTotal, ...]) -> FixedSheet:
    facts = {slot.slot_id: slot for slot in bound.snapshot.slots}
    used_ids = set(facts)
    emitted = set()
    local_number = count(1)
    slots = []
    cells = []
    for cell in bound.recipe.cells:
        local_ids = {}
        for slot_id in dict.fromkeys(cell.slots):
            packed_id = slot_id
            if slot_id in emitted:
                packed_id = f'cell-slot-{next(local_number)}'
                while packed_id in used_ids:
                    packed_id = f'cell-slot-{next(local_number)}'
                used_ids.add(packed_id)
            local_ids[slot_id] = packed_id
            fact = facts[slot_id]
            slots.append(FrozenSlot(packed_id, fact.revision, fact.count, fact.capacity))
        emitted.update(local_ids)
        cells.append(FrozenCell(cell.name, tuple(local_ids[slot_id] for slot_id in cell.slots)))
    basis = WritebackBasis(tuple(slots), tuple(cells))
    return FixedSheet(number, bound.snapshot.batch_id, bound.recipe.recipe_id, displays, basis)


def issue_sheet(
    issuer: sqlite3.Connection, source: sqlite3.Connection, batch_id: str, recipe_id: str,
) -> IssuedSheet:
    recipe = read_recipe(issuer, recipe_id)
    references = (slot for cell in recipe.cells for slot in cell.slots)
    snapshot = capture_snapshot(source, batch_id, references)
    bound = bind_recipe(recipe, snapshot)
    displays = calculate_totals(bound)
    sheet, piece = archive_sheet(issuer, lambda number: build_fixed_sheet(number, bound, displays))
    return IssuedSheet(sheet, piece)
