from itertools import product
import sqlite3

from corrections.apply import submit_edit
from corrections.orders import prepare_edit_order
from corrections.receipts import EditReceipt, read_receipt
from corrections.resolve import ResolutionStatus, resolve_edit
from intake.batches import import_batch
from sheets.accept import read_sheet
from sheets.archive import read_archived_sheet
from sheets.issue import issue_sheet
from source.commit import StaleRevision
from source.slots import read_slot
from tests.support import ABC_PIECE, WorkflowCase, defer_failure, displays, rows_for


class TestCorrections(WorkflowCase):
    def test_unique_joint_writeback_after_disconnect(self):
        old = self.pair()
        self.assertEqual(displays(read_sheet(old.piece)), [('ab', 10), ('bc', 10)])
        self.issuer.close()
        receipt = submit_edit(self.source, old.piece, {'ab': 12, 'bc': 0})
        self.assertIsInstance(receipt, EditReceipt)
        self.assert_slots({'A': 12, 'B': 0, 'C': 0}, 2)
        self.assertEqual(receipt.sheet_number, old.sheet.sheet_number)
        self.assertEqual(receipt.targets, (('ab', 12), ('bc', 0)))
        self.assertEqual([(s.slot_id, s.revision, s.count) for s in receipt.revisions],
                         [('A', 2, 12), ('B', 2, 0), ('C', 2, 0)])
        for name, initial in {'A': 4, 'B': 6, 'C': 4}.items():
            self.assertEqual(read_slot(self.source, name, 1).count, initial)
            self.assertEqual(read_slot(self.source, name).receipt_id, receipt.receipt_id)
        self.source.close()
        self.source = self.open_source()
        self.issuer = self.open_issuer()
        new = issue_sheet(self.issuer, self.source, 'batch', 'pair')
        self.assertEqual(displays(new.sheet), [('ab', 12), ('bc', 0)])
        self.assertEqual(displays(read_sheet(old.sheet.sheet_number, archive=self.issuer)),
                         [('ab', 10), ('bc', 10)])
        self.assertEqual(read_archived_sheet(self.issuer, old.sheet.sheet_number), old.piece)
        self.assertEqual(read_receipt(self.source, receipt.receipt_id), receipt)
        self.assert_no_receipt(receipt.receipt_id + 1)

    def test_independent_offline_fixed_piece(self):
        import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 6, 'C': 4}))
        self.issuer.close()
        self.assertEqual(displays(read_sheet(ABC_PIECE)), [('ab', 10), ('bc', 10)])
        receipt = submit_edit(self.source, ABC_PIECE, {'ab': 12, 'bc': 0})
        self.assertIsInstance(receipt, EditReceipt)
        self.assertEqual(receipt.sheet_number, 1)
        self.assert_slots({'A': 12, 'B': 0, 'C': 0}, 2)
        self.assertEqual(read_receipt(self.source, receipt.receipt_id), receipt)

    def test_partial_edit_keeps_related_cell(self):
        old = self.pair()
        self.issuer.close()
        self.assertIs(submit_edit(self.source, old.piece, {'ab': 12}), ResolutionStatus.MULTIPLE)
        self.assert_slots({'A': 4, 'B': 6, 'C': 4}, 1)
        self.assert_no_receipt()

    def test_unedited_row_forces_unique(self):
        old = self.pair()
        self.issuer.close()
        receipt = submit_edit(self.source, old.piece, {'ab': 0})
        self.assertIsInstance(receipt, EditReceipt)
        self.assertEqual(receipt.targets, (('ab', 0),))
        self.assert_slots({'A': 0, 'B': 0, 'C': 10}, 2)
        self.issuer = self.open_issuer()
        self.assertEqual(displays(issue_sheet(self.issuer, self.source, 'batch', 'pair').sheet),
                         [('ab', 0), ('bc', 10)])

    def test_transitive_closure(self):
        import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 6, 'C': 4, 'D': 6}))
        old = self.issue('chain', ('ab', ('A', 'B')), ('bc', ('B', 'C')), ('cd', ('C', 'D')), ('d', ('D',)))
        self.issuer.close()
        receipt = submit_edit(self.source, old.piece, {'ab': 12})
        self.assertIsInstance(receipt, EditReceipt)
        self.assert_slots({'A': 6, 'B': 6, 'C': 4, 'D': 6}, 2)
        self.assertEqual([s.slot_id for s in receipt.revisions], ['A', 'B', 'C', 'D'])
        self.issuer = self.open_issuer()
        self.assertEqual(displays(issue_sheet(self.issuer, self.source, 'batch', 'chain').sheet),
                         [('ab', 12), ('bc', 10), ('cd', 10), ('d', 6)])

    def test_bound_overflow_and_invalid_targets(self):
        old = self.pair()
        self.issuer.close()
        for targets in ({'ab': 13, 'bc': 0}, {'ab': -1}):
            with self.subTest(targets=targets):
                self.assertIs(submit_edit(self.source, old.piece, targets), ResolutionStatus.NO_SOLUTION)
        for targets in ({}, {'missing': 1}, {'ab': True}, {'ab': 2.5}):
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                submit_edit(self.source, old.piece, targets)
        self.assert_slots({'A': 4, 'B': 6, 'C': 4}, 1)
        self.assert_no_receipt()

    def test_integer_only_cycle_rejects(self):
        import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 6, 'C': 4}))
        old = self.issue('triangle', ('ab', ('A', 'B')), ('bc', ('B', 'C')), ('ca', ('C', 'A')))
        self.issuer.close()
        self.assertIs(submit_edit(self.source, old.piece, {'ab': 1, 'bc': 1, 'ca': 1}),
                      ResolutionStatus.NO_SOLUTION)
        self.assert_slots({'A': 4, 'B': 6, 'C': 4}, 1)
        self.assert_no_receipt()

    def test_even_cycle_conflict(self):
        import_batch(self.source, 'batch', rows_for(dict.fromkeys('ABCD', 4)))
        old = self.issue('ring', ('ab', ('A', 'B')), ('bc', ('B', 'C')),
                         ('cd', ('C', 'D')), ('da', ('D', 'A')))
        self.assertEqual(displays(old.sheet), [('ab', 8), ('bc', 8), ('cd', 8), ('da', 8)])
        self.issuer.close()
        self.assertIs(submit_edit(self.source, old.piece, {'ab': 9}), ResolutionStatus.NO_SOLUTION)
        self.assert_slots(dict.fromkeys('ABCD', 4), 1)
        self.assert_no_receipt()

    def test_revision_scope(self):
        import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 6, 'C': 4, 'D': 1}))
        old = self.issue('pair', ('ab', ('A', 'B')), ('bc', ('B', 'C')))
        same_value = self.issue('direct-b', ('b', ('B',)))
        unrelated = self.issue('direct-d', ('d', ('D',)))
        receipt = submit_edit(self.source, same_value.piece, {'b': 6})
        self.assertIsInstance(receipt, EditReceipt)
        self.assert_slots({'B': 6}, 2)
        with self.assertRaisesRegex(StaleRevision, "revision changed for 'B'"):
            submit_edit(self.source, old.piece, {'ab': 12, 'bc': 0})
        self.assert_slots({'A': 4, 'C': 4, 'D': 1}, 1)
        self.assert_slots({'B': 6}, 2)
        self.assert_no_receipt(receipt.receipt_id + 1)
        fresh = issue_sheet(self.issuer, self.source, 'batch', 'pair')
        self.issuer.close()
        unrelated_receipt = submit_edit(self.source, unrelated.piece, {'d': 2})
        self.assertIsInstance(unrelated_receipt, EditReceipt)
        joint = submit_edit(self.source, fresh.piece, {'ab': 12, 'bc': 0})
        self.assertIsInstance(joint, EditReceipt)
        self.assert_slots({'A': 12, 'C': 0, 'D': 2}, 2)
        self.assert_slots({'B': 0}, 3)
        self.assertEqual([s.slot_id for s in joint.revisions], ['A', 'B', 'C'])

    def test_writeback_commit_failure(self):
        old = self.pair()
        defer_failure(self.source, 'edit_receipts')
        self.issuer.close()
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            submit_edit(self.source, old.piece, {'ab': 12, 'bc': 0})
        self.source.close()
        self.source = self.open_source()
        self.assert_slots({'A': 4, 'B': 6, 'C': 4}, 1)
        for slot in 'ABC':
            with self.assertRaises(KeyError):
                read_slot(self.source, slot, 2)
        self.assert_no_receipt()
        self.issuer = self.open_issuer()
        self.assertEqual(read_archived_sheet(self.issuer, old.sheet.sheet_number), old.piece)
        self.assertEqual(displays(read_sheet(old.sheet.sheet_number, archive=self.issuer)),
                         [('ab', 10), ('bc', 10)])

    def test_components_and_repeated_reference(self):
        import_batch(self.source, 'batch', rows_for({'A': 0, 'B': 0, 'C': 0}))
        old = self.issue('disjoint', ('ab', ('A', 'B')), ('cc', ('C', 'C')))
        self.assertIs(submit_edit(self.source, old.piece, {'ab': 1, 'cc': 1}), ResolutionStatus.NO_SOLUTION)
        self.assertIs(submit_edit(self.source, old.piece, {'ab': 1, 'cc': 2}), ResolutionStatus.MULTIPLE)
        self.assert_no_receipt()
        receipt = submit_edit(self.source, old.piece, {'ab': 0, 'cc': 2})
        self.assertIsInstance(receipt, EditReceipt)
        self.assert_slots({'A': 0, 'B': 0, 'C': 1}, 2)

    def test_small_domains_against_independent_enumeration(self):
        import_batch(self.source, 'batch', rows_for({'A': 1, 'B': 1, 'C': 1}, capacity=2))
        old = self.issue('triangle', ('ab', ('A', 'B')), ('bc', ('B', 'C')), ('ca', ('C', 'A')))
        names = ('ab', 'bc', 'ca')
        for length in range(1, 4):
            for values in product(range(5), repeat=length):
                targets = dict(zip(names, values))
                ab, bc, ca = (*values, *([2] * (3 - length)))
                expected = [(a, b, c) for a, b, c in product(range(3), repeat=3)
                            if (a + b, b + c, c + a) == (ab, bc, ca)]
                with self.subTest(targets=targets):
                    result = resolve_edit(prepare_edit_order(old.piece, targets))
                    if not expected:
                        self.assertIs(result.status, ResolutionStatus.NO_SOLUTION)
                    elif len(expected) > 1:
                        self.assertIs(result.status, ResolutionStatus.MULTIPLE)
                    else:
                        self.assertIs(result.status, ResolutionStatus.UNIQUE)
                        self.assertEqual([(slot.slot_id, count) for slot, count in result.assignments],
                                         list(zip('ABC', expected[0])))
