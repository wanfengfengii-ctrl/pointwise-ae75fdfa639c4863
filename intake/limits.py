def require_integer(value: object, field: str) -> int:
    if type(value) is not int:
        raise ValueError(f'{field} must be an integer')
    return value


def validate_instrument_limit(value: object) -> int:
    capacity = require_integer(value, 'capacity')
    if capacity < 0:
        raise ValueError('capacity must be nonnegative')
    return capacity


def validate_pulse_count(value: object, capacity: int) -> int:
    count = require_integer(value, 'count')
    if not 0 <= count <= capacity:
        raise ValueError('count outside instrument capacity')
    return count


def encode_integer(value: int) -> str:
    return format(value, 'x')


def decode_integer(value: object) -> int:
    if not isinstance(value, str):
        raise ValueError('expected hexadecimal integer text')
    number = int(value, 16)
    if encode_integer(number) != value:
        raise ValueError('expected canonical hexadecimal integer text')
    return number
