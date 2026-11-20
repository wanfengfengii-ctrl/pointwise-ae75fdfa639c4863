from dataclasses import dataclass

from intake.limits import validate_instrument_limit, validate_pulse_count
from intake.origin import require_name
from rules.cells import CellDefinition
from rules.checks import validate_cell_definition
from rules.totals import CellTotal
from source.database import require_record_number


@dataclass(frozen=True, slots=True)
class FrozenSlot:
    slot_id: str
    revision: int
    count: int
    capacity: int


@dataclass(frozen=True, slots=True)
class FrozenCell:
    name: str
    slots: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WritebackBasis:
    slots: tuple[FrozenSlot, ...]
    cells: tuple[FrozenCell, ...]


def validate_basis(basis: WritebackBasis, displays: tuple[CellTotal, ...]) -> None:
    if not isinstance(basis, WritebackBasis) or not isinstance(displays, tuple):
        raise ValueError('expected fixed basis and ordered displays')
    if not isinstance(basis.slots, tuple) or not isinstance(basis.cells, tuple):
        raise ValueError('basis slots and cells must be immutable sequences')
    if not basis.cells or len(basis.cells) != len(displays):
        raise ValueError('basis cells and displays must be nonempty and aligned')
    counts = {}
    for slot in basis.slots:
        if not isinstance(slot, FrozenSlot):
            raise ValueError('invalid fixed slot')
        name = require_name(slot.slot_id, 'fixed slot')
        if name in counts:
            raise ValueError(f'duplicate fixed slot {name!r}')
        require_record_number(slot.revision, 'fixed revision')
        capacity = validate_instrument_limit(slot.capacity)
        counts[name] = validate_pulse_count(slot.count, capacity)
    seen = set()
    referenced = set()
    for cell, display in zip(basis.cells, displays):
        if not isinstance(cell, FrozenCell) or not isinstance(display, CellTotal):
            raise ValueError('invalid fixed cell or display')
        validate_cell_definition(CellDefinition(cell.name, cell.slots))
        if cell.name in seen or display.name != cell.name:
            raise ValueError('fixed cells must be distinct and follow display order')
        seen.add(cell.name)
        if any(slot not in counts for slot in cell.slots):
            raise ValueError(f'cell {cell.name!r} references missing fixed slot')
        if type(display.count) is not int or display.count != sum(counts[slot] for slot in cell.slots):
            raise ValueError(f'display for {cell.name!r} differs from its fixed counts')
        referenced.update(cell.slots)
    if referenced != counts.keys():
        raise ValueError('basis includes slots outside its cell references')
