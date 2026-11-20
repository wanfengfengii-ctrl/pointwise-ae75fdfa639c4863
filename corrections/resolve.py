from collections import defaultdict, deque
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


def _cell_groups(cells: tuple[FrozenCell, ...]) -> list[list[FrozenCell]]:
    """Group cells into components connected through shared slots."""
    parent = list(range(len(cells)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    owner = {}
    for index, cell in enumerate(cells):
        for slot_id in dict.fromkeys(cell.slots):
            if slot_id in owner:
                parent[find(index)] = find(owner[slot_id])
            else:
                owner[slot_id] = index
    groups = defaultdict(list)
    for index, cell in enumerate(cells):
        groups[find(index)].append(cell)
    return list(groups.values())


def _solve_group(
    group: list[FrozenCell], values: dict[str, int], slots: dict[str, FrozenSlot],
) -> tuple[ResolutionStatus, dict[str, int]]:
    """Solve one connected group exactly against the frozen capacities."""
    edges = []
    fixed = {}
    for cell in group:
        value = values[cell.name]
        first = cell.slots[0]
        if len(cell.slots) == 1 or cell.slots[1] == first:
            quotient, remainder = divmod(value, len(cell.slots))
            if remainder:
                return ResolutionStatus.NO_SOLUTION, {}
            if first in fixed:
                if fixed[first] != quotient:
                    return ResolutionStatus.NO_SOLUTION, {}
            else:
                fixed[first] = quotient
        else:
            edges.append((first, cell.slots[1], value))

    incident = defaultdict(list)
    for index, (left, right, _) in enumerate(edges):
        incident[left].append(index)
        incident[right].append(index)

    if fixed:
        # A repeated or single-slot cell pins one count; connectedness then
        # pins every count in the group. Each edge is checked once reached.
        queue = deque(fixed)
        while queue:
            slot_id = queue.popleft()
            for index in incident[slot_id]:
                left, right, value = edges[index]
                other = right if left == slot_id else left
                count = value - fixed[slot_id]
                if other in fixed:
                    if fixed[other] != count:
                        return ResolutionStatus.NO_SOLUTION, {}
                else:
                    fixed[other] = count
                    queue.append(other)
        if any(not 0 <= count <= slots[slot_id].capacity for slot_id, count in fixed.items()):
            return ResolutionStatus.NO_SOLUTION, {}
        return ResolutionStatus.UNIQUE, fixed

    # No pinning cell: every count is const + coef * t for a free integer t.
    coef = {}
    const = {}
    root = edges[0][0]
    coef[root], const[root] = 1, 0
    pinned = None
    queue = deque([root])
    while queue:
        slot_id = queue.popleft()
        for index in incident[slot_id]:
            left, right, value = edges[index]
            other = right if left == slot_id else left
            if other not in coef:
                coef[other] = -coef[slot_id]
                const[other] = value - const[slot_id]
                queue.append(other)
                continue
            combo = coef[left] + coef[right]
            residual = value - const[left] - const[right]
            if combo == 0:
                if residual != 0:
                    return ResolutionStatus.NO_SOLUTION, {}
                continue
            quotient, remainder = divmod(residual, combo)
            if remainder:
                return ResolutionStatus.NO_SOLUTION, {}
            if pinned is None:
                pinned = quotient
            elif pinned != quotient:
                return ResolutionStatus.NO_SOLUTION, {}

    if pinned is not None:
        solved = {slot_id: const[slot_id] + coef[slot_id] * pinned for slot_id in coef}
        if any(not 0 <= count <= slots[slot_id].capacity for slot_id, count in solved.items()):
            return ResolutionStatus.NO_SOLUTION, {}
        return ResolutionStatus.UNIQUE, solved

    lower = upper = None
    for slot_id in coef:
        capacity = slots[slot_id].capacity
        if coef[slot_id] == 1:
            low, high = -const[slot_id], capacity - const[slot_id]
        else:
            low, high = const[slot_id] - capacity, const[slot_id]
        lower = low if lower is None else max(lower, low)
        upper = high if upper is None else min(upper, high)
    if lower > upper:
        return ResolutionStatus.NO_SOLUTION, {}
    if lower == upper:
        return (ResolutionStatus.UNIQUE,
                {slot_id: const[slot_id] + coef[slot_id] * lower for slot_id in coef})
    return ResolutionStatus.MULTIPLE, {}


def resolve_edit(order: EditOrder) -> ResolvedAllocation:
    sheet = order.sheet
    slots = {slot.slot_id: slot for slot in sheet.basis.slots}
    values = {display.name: display.count for display in sheet.displays}
    values.update(order.targets)
    edited = {name for name, _ in order.targets}

    assignments = {}
    multiple = False
    for group in _cell_groups(sheet.basis.cells):
        if not any(cell.name in edited for cell in group):
            continue
        status, solved = _solve_group(group, values, slots)
        if status is ResolutionStatus.NO_SOLUTION:
            return ResolvedAllocation(ResolutionStatus.NO_SOLUTION)
        multiple |= status is ResolutionStatus.MULTIPLE
        assignments.update(solved)

    if multiple:
        return ResolvedAllocation(ResolutionStatus.MULTIPLE)
    return ResolvedAllocation(ResolutionStatus.UNIQUE,
                              tuple((slots[slot], assignments[slot]) for slot in sorted(assignments)))
