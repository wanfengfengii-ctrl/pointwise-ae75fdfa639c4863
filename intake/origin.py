from collections.abc import Mapping
from dataclasses import dataclass

from intake.limits import encode_integer, require_integer


@dataclass(frozen=True, slots=True)
class OriginRef:
    export: str
    line: int


def require_name(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f'{field} must be a nonempty name')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError(f'{field} must be valid UTF-8 text') from exc
    return value


def parse_origin(value: object) -> OriginRef:
    if not isinstance(value, Mapping) or set(value) != {'export', 'line'}:
        raise ValueError('origin must contain export and line')
    export = require_name(value['export'], 'origin export')
    line = require_integer(value['line'], 'origin line')
    if line < 1:
        raise ValueError('origin line must start at 1')
    return OriginRef(export, line)


def origin_record(origin: OriginRef) -> tuple[str, str]:
    return origin.export, encode_integer(origin.line)
