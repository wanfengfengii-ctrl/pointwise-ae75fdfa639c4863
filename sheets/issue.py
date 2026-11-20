from dataclasses import dataclass
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
    # V1 pieces key basis.slots by the original slot id and cells keep those
    # references, so slots shared between cells stay shared in the piece.
    slots = tuple(FrozenSlot(slot.slot_id, slot.revision, slot.count, slot.capacity)
                  for slot in bound.snapshot.slots)
    cells = tuple(FrozenCell(cell.name, cell.slots) for cell in bound.recipe.cells)
    basis = WritebackBasis(slots, cells)
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
