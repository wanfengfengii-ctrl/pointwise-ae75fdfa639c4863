from collections.abc import Mapping
from dataclasses import dataclass

from intake.limits import require_integer
from intake.origin import require_name
from sheets.accept import accept_fixed_sheet
from sheets.format import FixedSheet


@dataclass(frozen=True, slots=True)
class EditOrder:
    sheet: FixedSheet
    targets: tuple[tuple[str, int], ...]


def parse_edit_targets(sheet: FixedSheet, targets: Mapping[str, int]) -> tuple[tuple[str, int], ...]:
    if not isinstance(targets, Mapping) or not targets:
        raise ValueError('edit requires a nonempty mapping of cell targets')
    cells = {cell.name for cell in sheet.displays}
    parsed = []
    for name, value in targets.items():
        require_name(name, 'target cell')
        if name not in cells:
            raise ValueError(f'unknown target cell {name!r}')
        parsed.append((name, require_integer(value, 'target count')))
    return tuple(parsed)


def prepare_edit_order(piece: bytes | FixedSheet, targets: Mapping[str, int]) -> EditOrder:
    sheet = accept_fixed_sheet(piece)
    return EditOrder(sheet, parse_edit_targets(sheet, targets))
