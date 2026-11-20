"""Regressions for the parallel-sample pulse review writeback chain.

Root cause of the repaired defect: issued pieces renamed shared slots
(`cell-slot-N`), so jointly edited cells looked disconnected and the joint
order was misjudged; the resolver also propagated a greedy lower bound instead
of solving the connected group exactly against the frozen capacities.
"""
from corrections.apply import submit_edit
from corrections.receipts import EditReceipt, read_receipt
from corrections.resolve import ResolutionStatus
from intake.batches import import_batch
from sheets.accept import read_sheet
from tests.support import WorkflowCase, rows_for


class TestResolutionRegression(WorkflowCase):
    def test_unedited_disconnected_group_keeps_its_revision(self):
        import_batch(self.source, 'batch', rows_for({'A': 0, 'B': 0, 'C': 0}))
        old = self.issue('disjoint', ('ab', ('A', 'B')), ('cc', ('C', 'C')))
        self.issuer.close()
        receipt = submit_edit(self.source, old.piece, {'cc': 2})
        self.assertIsInstance(receipt, EditReceipt)
        self.assertEqual([slot.slot_id for slot in receipt.revisions], ['C'])
        self.assert_slots({'C': 1}, 2)
        self.assert_slots({'A': 0, 'B': 0}, 1)
        self.assertEqual(read_receipt(self.source, receipt.receipt_id), receipt)

    def test_capacity_bounds_pin_edge_group(self):
        import_batch(self.source, 'batch', rows_for({'A': 1, 'B': 1}, capacity=2))
        old = self.issue('edge', ('ab', ('A', 'B')))
        self.issuer.close()
        self.assertIs(submit_edit(self.source, old.piece, {'ab': 5}), ResolutionStatus.NO_SOLUTION)
        self.assertIs(submit_edit(self.source, old.piece, {'ab': 3}), ResolutionStatus.MULTIPLE)
        self.assert_slots({'A': 1, 'B': 1}, 1)
        self.assert_no_receipt()
        receipt = submit_edit(self.source, old.piece, {'ab': 4})
        self.assertIsInstance(receipt, EditReceipt)
        self.assert_slots({'A': 2, 'B': 2}, 2)
        self.assertEqual(read_receipt(self.source, receipt.receipt_id), receipt)

    def test_joint_piece_survives_reopen_and_partial_target_stays_multiple(self):
        self.pair()
        self.issuer.close()
        self.issuer = self.open_issuer()
        piece = read_sheet(1, archive=self.issuer)
        self.assertEqual([cell.slots for cell in piece.basis.cells], [('A', 'B'), ('B', 'C')])
        self.assertIs(submit_edit(self.source, piece, {'ab': 12}), ResolutionStatus.MULTIPLE)
        self.assert_no_receipt()
        receipt = submit_edit(self.source, piece, {'ab': 12, 'bc': 0})
        self.assertIsInstance(receipt, EditReceipt)
        self.assert_slots({'A': 12, 'B': 0, 'C': 0}, 2)
