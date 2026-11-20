from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CellDefinition:
    name: str
    slots: tuple[str, ...]


def parse_cell_definition(value: object) -> CellDefinition:
    if isinstance(value, CellDefinition):
        return value
    if not isinstance(value, Mapping) or set(value) != {'name', 'slots'}:
        raise ValueError('cell must contain name and slots')
    references = value['slots']
    if not isinstance(references, (list, tuple)):
        raise ValueError('cell slots must be an ordered list or tuple')
    return CellDefinition(value['name'], tuple(references))
