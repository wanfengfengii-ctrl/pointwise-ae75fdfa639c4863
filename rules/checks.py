from collections.abc import Iterable

from intake.origin import require_name
from rules.cells import CellDefinition, parse_cell_definition


def validate_cell_definition(cell: CellDefinition) -> None:
    require_name(cell.name, 'cell')
    if not isinstance(cell.slots, tuple) or len(cell.slots) not in (1, 2):
        raise ValueError(f'cell {cell.name!r} requires one or two slot references')
    for slot in cell.slots:
        require_name(slot, 'slot reference')


def validate_recipe(recipe_id: str, cells: Iterable[object]) -> tuple[CellDefinition, ...]:
    require_name(recipe_id, 'recipe')
    if not isinstance(cells, Iterable):
        raise ValueError('recipe cells must be an ordered iterable')
    parsed = []
    names = set()
    for value in cells:
        cell = parse_cell_definition(value)
        validate_cell_definition(cell)
        if cell.name in names:
            raise ValueError(f'duplicate cell {cell.name!r}')
        parsed.append(cell)
        names.add(cell.name)
    if not parsed:
        raise ValueError('recipe must have at least one cell')
    return tuple(parsed)
