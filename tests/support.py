from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from corrections.receipts import read_receipt
from intake.batches import import_batch
from rules.catalog import register_recipe
from sheets.archive import open_issuance_database
from sheets.issue import issue_sheet
from source.database import open_source_database
from source.slots import read_slot


ABC_PIECE = b'''{
  "version": 1, "sheet_number": 1, "batch_id": "batch", "recipe_id": "pair",
  "displays": [{"name": "ab", "count": "a"}, {"name": "bc", "count": "a"}],
  "basis": {
    "slots": {
      "A": {"revision": 1, "count": "4", "capacity": "c"},
      "B": {"revision": 1, "count": "6", "capacity": "c"},
      "C": {"revision": 1, "count": "4", "capacity": "c"}
    },
    "cells": [{"name": "ab", "slots": ["A", "B"]}, {"name": "bc", "slots": ["B", "C"]}]
  }
}'''


def rows_for(counts, capacity=12, export='counter/shift-one'):
    return [{'slot': slot, 'capacity': capacity, 'count': count,
             'origin': {'export': export, 'line': line}}
            for line, (slot, count) in enumerate(counts.items(), start=1)]


def displays(sheet):
    return [(cell.name, cell.count) for cell in sheet.displays]


def defer_failure(db: sqlite3.Connection, table: str) -> None:
    # The insert completes. SQLite enforces this foreign key at the real COMMIT.
    if table not in {'edit_receipts', 'fixed_sheets'}:
        raise ValueError('unknown failure fixture table')
    db.execute('CREATE TABLE test_gate (id INTEGER PRIMARY KEY)')
    db.execute('''CREATE TABLE test_pending (
                    gate INTEGER REFERENCES test_gate(id) DEFERRABLE INITIALLY DEFERRED
                  )''')
    db.execute(f'''CREATE TRIGGER test_reject_commit AFTER INSERT ON {table}
                   BEGIN INSERT INTO test_pending (gate) VALUES (1); END''')


class WorkflowCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.source_path = Path(directory.name) / 'source.sqlite'
        self.issuer_path = Path(directory.name) / 'issuer.sqlite'
        self.source = self.open_source()
        self.issuer = self.open_issuer()

    def open_source(self):
        db = open_source_database(self.source_path)
        self.addCleanup(db.close)
        return db

    def open_issuer(self):
        db = open_issuance_database(self.issuer_path)
        self.addCleanup(db.close)
        return db

    def issue(self, recipe, *cells, batch='batch'):
        register_recipe(self.issuer, recipe, [{'name': name, 'slots': slots} for name, slots in cells])
        return issue_sheet(self.issuer, self.source, batch, recipe)

    def pair(self):
        import_batch(self.source, 'batch', rows_for({'A': 4, 'B': 6, 'C': 4}))
        return self.issue('pair', ('ab', ('A', 'B')), ('bc', ('B', 'C')))

    def assert_slots(self, counts, revision):
        actual = {slot: read_slot(self.source, slot) for slot in counts}
        self.assertEqual({slot: value.count for slot, value in actual.items()}, counts)
        self.assertEqual({value.revision for value in actual.values()}, {revision})

    def assert_no_receipt(self, receipt_id=1):
        with self.assertRaises(KeyError):
            read_receipt(self.source, receipt_id)
