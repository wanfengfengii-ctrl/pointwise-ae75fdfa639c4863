import sqlite3

from corrections.apply import submit_edit
from corrections.receipts import EditReceipt
from intake.batches import BatchConflict, import_batch, read_original_batch
from intake.origin import OriginRef
from source.slots import read_slot
from tests.support import WorkflowCase, rows_for


class TestIntake(WorkflowCase):
    def assert_batch_absent(self, batch, *slots):
        with self.assertRaises(KeyError):
            read_original_batch(self.source, batch)
        for slot in slots:
            with self.assertRaises(KeyError):
                read_slot(self.source, slot)

    def test_import_replay_after_correction(self):
        rows = rows_for({'A': 4, 'B': 6})
        original = import_batch(self.source, 'batch', rows)
        issued = self.issue('direct', ('b', ('B',)))
        receipt = submit_edit(self.source, issued.piece, {'b': 8})
        self.assertIsInstance(receipt, EditReceipt)
        current = read_slot(self.source, 'B')
        self.assertEqual((current.count, current.revision, current.receipt_id), (8, 2, receipt.receipt_id))
        self.source.close()
        self.source = self.open_source()
        self.assertEqual(import_batch(self.source, 'batch', rows), original)
        self.assertEqual(read_original_batch(self.source, 'batch'), original)
        self.assertEqual(read_slot(self.source, 'B'), current)
        first = read_slot(self.source, 'B', 1)
        self.assertEqual((first.count, first.revision, first.receipt_id), (6, 1, None))
        self.assertEqual(first.origin, OriginRef('counter/shift-one', 2))
        self.assertEqual(current.origin, first.origin)

    def test_batch_id_conflict(self):
        rows = rows_for({'A': 4, 'B': 6})
        original = import_batch(self.source, 'batch', rows)
        for changed in (list(reversed(rows)), rows_for({'A': 4, 'B': 5}),
                        rows_for({'A': 4, 'B': 6}, export='another export')):
            with self.subTest(rows=changed), self.assertRaises(BatchConflict):
                import_batch(self.source, 'batch', changed)
        self.assertEqual(read_original_batch(self.source, 'batch'), original)
        self.assert_slots({'A': 4, 'B': 6}, 1)

    def test_out_of_range_rejects_batch(self):
        with self.assertRaisesRegex(ValueError, 'row 2.*capacity'):
            import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 13}))
        self.assert_batch_absent('batch', 'A', 'B')

    def test_reject_fraction_and_boolean(self):
        for invalid in (12.5, True, None, '12'):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, 'row 2.*integer'):
                    import_batch(self.source, 'batch', rows_for({'A': 4, 'B': invalid}))
                self.assert_batch_absent('batch', 'A', 'B')

    def test_zero_and_cap_with_missing_count(self):
        rows = rows_for({'A': 0, 'B': 12})
        rows[0]['capacity'] = 0
        incomplete = [rows[0], {key: value for key, value in rows[1].items() if key != 'count'}]
        with self.assertRaisesRegex(ValueError, 'row 2'):
            import_batch(self.source, 'batch', incomplete)
        self.assert_batch_absent('batch', 'A', 'B')
        import_batch(self.source, 'batch', rows)
        self.assert_slots({'A': 0, 'B': 12}, 1)
        self.assertEqual(read_slot(self.source, 'A').capacity, 0)

    def test_late_slot_collision_rolls_back_original_and_first_row(self):
        import_batch(self.source, 'earlier', rows_for({'B': 6}))
        with self.assertRaises(BatchConflict):
            import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 5}))
        self.assert_batch_absent('batch', 'A')
        self.assert_slots({'B': 6}, 1)

    def test_source_error_after_first_slot_leaves_no_batch(self):
        self.source.execute('''CREATE TRIGGER reject_second_slot BEFORE INSERT ON slots
                               WHEN NEW.slot_id = 'B'
                               BEGIN SELECT RAISE(ABORT, 'instrument register unavailable'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'instrument register unavailable'):
            import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 6}))
        self.source.close()
        self.source = self.open_source()
        self.assert_batch_absent('batch', 'A', 'B')
