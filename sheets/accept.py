import sqlite3

from sheets.archive import read_archived_sheet
from sheets.format import FixedSheet, decode_sheet, validate_sheet


def accept_fixed_sheet(piece: bytes | FixedSheet) -> FixedSheet:
    sheet = piece if isinstance(piece, FixedSheet) else decode_sheet(piece)
    validate_sheet(sheet)
    return sheet


def read_sheet(
    subject: int | bytes | FixedSheet, *, archive: sqlite3.Connection | None = None,
) -> FixedSheet:
    if type(subject) is int:
        if archive is None:
            raise ValueError('reading a sheet number requires the issuing archive')
        sheet = accept_fixed_sheet(read_archived_sheet(archive, subject))
        if sheet.sheet_number != subject:
            raise ValueError('archive returned a different sheet number')
        return sheet
    return accept_fixed_sheet(subject)
