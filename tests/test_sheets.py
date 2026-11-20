import json
import sqlite3

from corrections.apply import submit_edit
from corrections.receipts import EditReceipt
from intake.batches import import_batch
from rules.catalog import RecipeConflict, register_recipe
from sheets.accept import read_sheet
from sheets.archive import read_archived_sheet
from sheets.issue import issue_sheet
from tests.support import WorkflowCase, defer_failure, displays, rows_for


class TestSheets(WorkflowCase):
    def test_sheet_preserves_shared_source(self):
        import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 6, 'C': 4, 'Z': 0}))
        issued = self.issue('pair', ('bc', ('B', 'C')), ('zero', ('Z',)), ('ab', ('A', 'B')))
        self.issuer.close()
        sheet = read_sheet(issued.piece)
        self.assertEqual(displays(sheet), [('bc', 10), ('zero', 0), ('ab', 10)])
        self.assertEqual([(cell.name, cell.slots) for cell in sheet.basis.cells],
                         [('bc', ('B', 'C')), ('zero', ('Z',)), ('ab', ('A', 'B'))])
        self.assertEqual(sum(slot.slot_id == 'B' for slot in sheet.basis.slots), 1)
        b = next(slot for slot in sheet.basis.slots if slot.slot_id == 'B')
        self.assertEqual((b.capacity, b.count, b.revision), (12, 6, 1))
        self.issuer = self.open_issuer()
        self.assertEqual(read_sheet(sheet.sheet_number, archive=self.issuer), sheet)
        self.assertEqual(read_archived_sheet(self.issuer, sheet.sheet_number), issued.piece)

    def test_recipe_binding(self):
        import_batch(self.source, 'batch', rows_for({'A': 4}))
        import_batch(self.source, 'another', rows_for({'B': 6}))
        bad_definitions = ([{'name': 'x', 'slots': []}],
                           [{'name': 'x', 'slots': ['A', 'B', 'C']}],
                           [{'name': 'x', 'slots': ['A']}, {'name': 'x', 'slots': ['B']}])
        for cells in bad_definitions:
            with self.subTest(cells=cells), self.assertRaises(ValueError):
                register_recipe(self.issuer, 'invalid', cells)
        with self.assertRaises(KeyError):
            issue_sheet(self.issuer, self.source, 'batch', 'invalid')
        with self.assertRaisesRegex(ValueError, 'outside batch'):
            self.issue('cross', ('ab', ('A', 'B')))
        with self.assertRaises(KeyError):
            self.issue('missing', ('missing', ('X',)))
        with self.assertRaises(KeyError):
            read_sheet(1, archive=self.issuer)
        chosen = [{'name': 'a', 'slots': ['A']}]
        self.assertEqual(register_recipe(self.issuer, 'direct', chosen),
                         register_recipe(self.issuer, 'direct', chosen))
        with self.assertRaises(RecipeConflict):
            register_recipe(self.issuer, 'direct', [{'name': 'b', 'slots': ['B']}])
        valid = issue_sheet(self.issuer, self.source, 'batch', 'direct')
        self.assertEqual(valid.sheet.sheet_number, 1)
        self.assertEqual(displays(valid.sheet), [('a', 4)])

    def test_snapshot_consistency(self):
        import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 6}))
        original = self.issue('direct', ('a', ('A',)), ('b', ('B',)))
        writer = self.open_source()
        results = []
        errors = []

        def write_before_second_slot(statement):
            if results or errors:
                return
            if statement.startswith('SELECT slot_id, batch_id, capacity, export_id, line_number, current_revision') and "WHERE slot_id = 'B'" in statement:
                try:
                    results.append(submit_edit(writer, original.piece, {'a': 1, 'b': 2}))
                except Exception as exc:
                    errors.append(exc)

        self.source.set_trace_callback(write_before_second_slot)
        try:
            concurrent = issue_sheet(self.issuer, self.source, 'batch', 'direct')
        finally:
            self.source.set_trace_callback(None)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], EditReceipt)
        self.assertEqual(displays(concurrent.sheet), [('a', 4), ('b', 6)])
        self.assertEqual([slot.revision for slot in concurrent.sheet.basis.slots], [1, 1])
        self.assert_slots({'A': 1, 'B': 2}, 2)

    def test_integer_sum_and_fixed_roundtrip(self):
        large = 1 << 16000
        import_batch(self.source, 'batch', rows_for({'A': large + 5, 'B': large + 7}, large + 8))
        issued = self.issue('wide', ('ab', ('A', 'B')))
        self.source.close()
        self.source = self.open_source()
        self.assert_slots({'A': large + 5, 'B': large + 7}, 1)
        self.assertEqual(displays(read_sheet(issued.piece)), [('ab', (1 << 16001) + 12)])
        self.issuer.close()
        self.issuer = self.open_issuer()
        self.assertEqual(displays(read_sheet(issued.sheet.sheet_number, archive=self.issuer)),
                         [('ab', (1 << 16001) + 12)])

    def test_invalid_fixed_content(self):
        issued = self.pair()
        missing = json.loads(issued.piece)
        del missing['basis']['slots']['B']
        broken = json.loads(issued.piece)
        broken['displays'][0]['count'] = 'b'
        invalid_limit = json.loads(issued.piece)
        invalid_limit['basis']['slots']['B']['capacity'] = '5'
        for bad in (missing, broken, invalid_limit):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                read_sheet(json.dumps(bad).encode('utf-8'))
        for bad_piece in (b'{', b'\xff', issued.piece.replace(b'"version":1', b'"version":1,"version":1')):
            with self.subTest(bad_piece=bad_piece), self.assertRaises(ValueError):
                read_sheet(bad_piece)

    def test_issue_rollback(self):
        first = self.pair()
        defer_failure(self.issuer, 'fixed_sheets')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            issue_sheet(self.issuer, self.source, 'batch', 'pair')
        self.issuer.close()
        self.issuer = self.open_issuer()
        self.assertEqual(read_archived_sheet(self.issuer, first.sheet.sheet_number), first.piece)
        with self.assertRaises(KeyError):
            read_sheet(first.sheet.sheet_number + 1, archive=self.issuer)

    def test_exact_old_number(self):
        old = self.pair()
        result = submit_edit(self.source, old.piece, {'ab': 12, 'bc': 0})
        self.assertIsInstance(result, EditReceipt)
        new = issue_sheet(self.issuer, self.source, 'batch', 'pair')
        self.issuer.close()
        self.issuer = self.open_issuer()
        self.assertNotEqual(old.sheet.sheet_number, new.sheet.sheet_number)
        self.assertEqual(displays(read_sheet(old.sheet.sheet_number, archive=self.issuer)),
                         [('ab', 10), ('bc', 10)])
        self.assertEqual(displays(read_sheet(new.sheet.sheet_number, archive=self.issuer)),
                         [('ab', 12), ('bc', 0)])
        with self.assertRaises(KeyError):
            read_sheet(new.sheet.sheet_number + 1, archive=self.issuer)
