from collections.abc import Iterable
from dataclasses import dataclass
import json
import sqlite3

from intake.origin import require_name
from rules.cells import CellDefinition
from rules.checks import validate_recipe
from source.database import source_write_transaction


class RecipeConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Recipe:
    recipe_id: str
    cells: tuple[CellDefinition, ...]


def initialize_recipe_schema(db: sqlite3.Connection) -> None:
    db.execute('''CREATE TABLE IF NOT EXISTS recipes (
                      recipe_id TEXT PRIMARY KEY NOT NULL,
                      definition TEXT NOT NULL
                  )''')


def read_recipe(db: sqlite3.Connection, recipe_id: str) -> Recipe:
    recipe_id = require_name(recipe_id, 'recipe')
    record = db.execute('SELECT definition FROM recipes WHERE recipe_id = ?', (recipe_id,)).fetchone()
    if record is None:
        raise KeyError(recipe_id)
    cells = validate_recipe(recipe_id, json.loads(record[0]))
    return Recipe(recipe_id, cells)


def register_recipe(db: sqlite3.Connection, recipe_id: str, cells: Iterable[object]) -> Recipe:
    recipe = Recipe(recipe_id, validate_recipe(recipe_id, cells))
    definition = json.dumps([{'name': cell.name, 'slots': cell.slots} for cell in recipe.cells],
                            ensure_ascii=False, separators=(',', ':'))
    with source_write_transaction(db):
        existing = db.execute('SELECT definition FROM recipes WHERE recipe_id = ?', (recipe_id,)).fetchone()
        if existing is not None:
            if existing[0] != definition:
                raise RecipeConflict(f'recipe {recipe_id!r} is already registered with another definition')
        else:
            db.execute('INSERT INTO recipes (recipe_id, definition) VALUES (?, ?)', (recipe_id, definition))
    return recipe
