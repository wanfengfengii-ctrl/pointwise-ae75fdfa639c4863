from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from intake.limits import validate_instrument_limit, validate_pulse_count
from intake.origin import OriginRef, parse_origin, require_name


@dataclass(frozen=True, slots=True)
class ParsedSlotRow:
    slot_id: str
    capacity: int
    count: int
    origin: OriginRef


@dataclass(frozen=True, slots=True)
class ParsedBatch:
    batch_id: str
    rows: tuple[ParsedSlotRow, ...]


def parse_batch(batch_id: str, rows: Iterable[Mapping]) -> ParsedBatch:
    batch_id = require_name(batch_id, 'batch')
    if not isinstance(rows, Iterable) or isinstance(rows, (str, bytes, Mapping)):
        raise ValueError('batch rows must be an ordered iterable of records')
    parsed = []
    seen = set()
    for position, row in enumerate(rows, start=1):
        try:
            if not isinstance(row, Mapping) or set(row) != {'slot', 'capacity', 'count', 'origin'}:
                raise ValueError('row must contain slot, capacity, count and origin')
            slot_id = require_name(row['slot'], 'slot')
            if slot_id in seen:
                raise ValueError(f'duplicate slot {slot_id!r}')
            capacity = validate_instrument_limit(row['capacity'])
            count = validate_pulse_count(row['count'], capacity)
            origin = parse_origin(row['origin'])
        except ValueError as exc:
            raise ValueError(f'batch {batch_id!r}, row {position}: {exc}') from exc
        parsed.append(ParsedSlotRow(slot_id, capacity, count, origin))
        seen.add(slot_id)
    if not parsed:
        raise ValueError('batch must contain at least one row')
    return ParsedBatch(batch_id, tuple(parsed))
