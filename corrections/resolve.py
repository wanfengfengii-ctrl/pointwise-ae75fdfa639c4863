from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from corrections.orders import EditOrder
from sheets.basis import FrozenCell, FrozenSlot


class ResolutionStatus(StrEnum):
    NO_SOLUTION = 'NO_SOLUTION'
    MULTIPLE = 'MULTIPLE'
    UNIQUE = 'UNIQUE'


@dataclass(frozen=True, slots=True)
class ResolvedAllocation:
    status: ResolutionStatus
    assignments: tuple[tuple[FrozenSlot, int], ...] = ()


def _cell_proposal(
    cell: FrozenCell, target: int, slots: dict[str, FrozenSlot],
) -> tuple[dict[str, int] | None, bool]:
    first = cell.slots[0]
    if len(cell.slots) == 1 or first == cell.slots[1]:
        value, remainder = divmod(target, len(cell.slots))
        if remainder or not 0 <= value <= slots[first].capacity:
            return None, False
        return {first: value}, False

    second = cell.slots[1]
    lower = max(0, target - slots[second].capacity)
    upper = min(slots[first].capacity, target)
    if lower > upper:
        return None, False
    return {first: lower, second: target - lower}, lower != upper


def resolve_edit(order: EditOrder) -> ResolvedAllocation:
    sheet = order.sheet
    slots = {slot.slot_id: slot for slot in sheet.basis.slots}
    cells = {cell.name: cell for cell in sheet.basis.cells}
    values = {display.name: display.count for display in sheet.displays}
    values.update(order.targets)
    incident = defaultdict(list)
    for cell in sheet.basis.cells:
        for slot in dict.fromkeys(cell.slots):
            incident[slot].append(cell)

    pending = [cells[name] for name, _ in reversed(order.targets)]
    visited = set()
    assignments = {}
    multiple = False
    while pending:
        cell = pending.pop()
        if cell.name in visited:
            continue
        visited.add(cell.name)
        proposed, has_choices = _cell_proposal(cell, values[cell.name], slots)
        if proposed is None:
            return ResolvedAllocation(ResolutionStatus.NO_SOLUTION)
        for slot, count in proposed.items():
            if slot in assignments:
                if assignments[slot] != count:
                    return ResolvedAllocation(ResolutionStatus.NO_SOLUTION)
            else:
                assignments[slot] = count
                pending.extend(incident[slot])
        multiple |= has_choices

    if multiple:
        return ResolvedAllocation(ResolutionStatus.MULTIPLE)
    return ResolvedAllocation(ResolutionStatus.UNIQUE,
                              tuple((slots[slot], assignments[slot]) for slot in sorted(assignments)))
