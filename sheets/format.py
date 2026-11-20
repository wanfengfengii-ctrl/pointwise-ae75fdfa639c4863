from dataclasses import dataclass
import json

from intake.limits import decode_integer, encode_integer
from intake.origin import require_name
from rules.totals import CellTotal
from sheets.basis import FrozenCell, FrozenSlot, WritebackBasis, validate_basis
from source.database import require_record_number


@dataclass(frozen=True, slots=True)
class FixedSheet:
    sheet_number: int
    batch_id: str
    recipe_id: str
    displays: tuple[CellTotal, ...]
    basis: WritebackBasis


def validate_sheet(sheet: FixedSheet) -> None:
    require_record_number(sheet.sheet_number, 'sheet number')
    require_name(sheet.batch_id, 'sheet batch')
    require_name(sheet.recipe_id, 'sheet recipe')
    validate_basis(sheet.basis, sheet.displays)


def encode_sheet(sheet: FixedSheet) -> bytes:
    validate_sheet(sheet)
    payload = {
        'version': 1,
        'sheet_number': sheet.sheet_number,
        'batch_id': sheet.batch_id,
        'recipe_id': sheet.recipe_id,
        'displays': [{'name': cell.name, 'count': encode_integer(cell.count)} for cell in sheet.displays],
        'basis': {
            'slots': {
                slot.slot_id: {'revision': slot.revision, 'count': encode_integer(slot.count),
                               'capacity': encode_integer(slot.capacity)}
                for slot in sheet.basis.slots
            },
            'cells': [{'name': cell.name, 'slots': cell.slots} for cell in sheet.basis.cells],
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate fixed-piece field {key!r}')
        result[key] = value
    return result


def _object(value: object, *fields: str) -> dict:
    if not isinstance(value, dict) or value.keys() != set(fields):
        raise ValueError(f'expected fixed-piece object with fields {fields}')
    return value


def _array(value: object) -> list:
    if not isinstance(value, list):
        raise ValueError('expected fixed-piece array')
    return value


def _decode_display(value: object) -> CellTotal:
    item = _object(value, 'name', 'count')
    return CellTotal(item['name'], decode_integer(item['count']))


def _decode_slot(name: str, value: object) -> FrozenSlot:
    item = _object(value, 'revision', 'count', 'capacity')
    return FrozenSlot(name, item['revision'], decode_integer(item['count']), decode_integer(item['capacity']))


def _decode_cell(value: object) -> FrozenCell:
    item = _object(value, 'name', 'slots')
    return FrozenCell(item['name'], tuple(_array(item['slots'])))


def decode_sheet(piece: bytes) -> FixedSheet:
    if not isinstance(piece, bytes):
        raise ValueError('fixed piece must be bytes')
    try:
        payload = json.loads(piece.decode('utf-8'), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('invalid fixed-piece JSON') from exc
    item = _object(payload, 'version', 'sheet_number', 'batch_id', 'recipe_id', 'displays', 'basis')
    if type(item['version']) is not int or item['version'] != 1:
        raise ValueError('unsupported fixed-piece version')
    basis = _object(item['basis'], 'slots', 'cells')
    if not isinstance(basis['slots'], dict):
        raise ValueError('expected a fixed-slot object keyed by slot name')
    slots = tuple(_decode_slot(name, value) for name, value in basis['slots'].items())
    cells = tuple(_decode_cell(value) for value in _array(basis['cells']))
    displays = tuple(_decode_display(value) for value in _array(item['displays']))
    return FixedSheet(item['sheet_number'], item['batch_id'], item['recipe_id'], displays,
                      WritebackBasis(slots, cells))
