from dataclasses import dataclass

from rules.binding import BoundRecipe


@dataclass(frozen=True, slots=True)
class CellTotal:
    name: str
    count: int


def calculate_totals(bound: BoundRecipe) -> tuple[CellTotal, ...]:
    counts = {slot.slot_id: slot.count for slot in bound.snapshot.slots}
    return tuple(CellTotal(cell.name, sum(counts[slot] for slot in cell.slots))
                 for cell in bound.recipe.cells)
