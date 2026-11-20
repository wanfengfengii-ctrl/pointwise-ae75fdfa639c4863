from contextlib import closing
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from corrections.apply import submit_edit
from corrections.receipts import EditReceipt, read_receipt
from corrections.resolve import ResolutionStatus
from intake.batches import import_batch
from rules.catalog import register_recipe
from sheets.accept import read_sheet
from sheets.archive import open_issuance_database
from sheets.issue import issue_sheet
from source.commit import StaleRevision
from source.database import open_source_database
from source.slots import read_slot


def main() -> int:
    initial = {'A': 4, 'B': 6, 'C': 4}
    rows = [{'slot': slot, 'capacity': 12, 'count': count,
             'origin': {'export': 'counter-shift-one', 'line': line}}
            for line, (slot, count) in enumerate(initial.items(), start=1)]
    targets = {'ab': 12, 'bc': 0}
    expected = {'A': 12, 'B': 0, 'C': 0}
    downstream_expected = {'old': [10, 10], 'new': [12, 0], 'receipt_revisions': [2, 2, 2]}
    with TemporaryDirectory() as directory:
        source_path = Path(directory) / 'source.sqlite'
        issuer_path = Path(directory) / 'issuer.sqlite'
        with closing(open_source_database(source_path)) as source:
            import_batch(source, 'morning', rows)
            with closing(open_issuance_database(issuer_path)) as issuer:
                register_recipe(issuer, 'pair', [{'name': 'ab', 'slots': ['A', 'B']},
                                                 {'name': 'bc', 'slots': ['B', 'C']}])
                original = issue_sheet(issuer, source, 'morning', 'pair')
            try:
                result = submit_edit(source, original.piece, targets)
            except StaleRevision as exc:
                print(f'JOINT_CORRECTION_REJECTED {exc}', file=sys.stderr)
                return 1
            if isinstance(result, ResolutionStatus):
                print(f'JOINT_CORRECTION_REJECTED {result.value}', file=sys.stderr)
                return 1
            if not isinstance(result, EditReceipt):
                raise TypeError('unexpected writeback response')
        with closing(open_source_database(source_path)) as source, closing(open_issuance_database(issuer_path)) as issuer:
            reopened_receipt = read_receipt(source, result.receipt_id)
            if reopened_receipt != result:
                raise AssertionError('receipt changed after reopening')
            old = read_sheet(original.sheet.sheet_number, archive=issuer)
            new = issue_sheet(issuer, source, 'morning', 'pair').sheet
            actual = {slot: read_slot(source, slot).count for slot in initial}
            downstream = {
                'old': [cell.count for cell in old.displays],
                'new': [cell.count for cell in new.displays],
                'receipt_revisions': [slot.revision for slot in reopened_receipt.revisions],
            }
            if actual != expected or downstream != downstream_expected:
                raise AssertionError(f'writeback or reconciliation mismatch: {actual!r} {downstream!r}')
            print(f'旧表 {old.sheet_number} {downstream["old"]}，新表 {new.sheet_number} {downstream["new"]}')
            print(f'回执 {reopened_receipt.receipt_id}，当前槽 {actual}')
    observation = {
        'case_id': 'n4',
        'input': {'initial': initial, 'capacity': 12, 'targets': targets},
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream,
        'code_paths': ['sheets/issue.py', 'corrections/resolve.py', 'source/commit.py', 'corrections/receipts.py'],
        'oracle': 'B+C=0 with nonnegative counts implies B=C=0. A+B=12 then fixes A=12. First revisions advance once.',
    }
    print('POINTWISE_SCENARIO ' + json.dumps(observation, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
