from dataclasses import dataclass

from rules.catalog import Recipe
from source.snapshot import BatchSnapshot


@dataclass(frozen=True, slots=True)
class BoundRecipe:
    recipe: Recipe
    snapshot: BatchSnapshot


def bind_recipe(recipe: Recipe, snapshot: BatchSnapshot) -> BoundRecipe:
    captured = {slot.slot_id for slot in snapshot.slots}
    for cell in recipe.cells:
        for slot in cell.slots:
            if slot not in captured:
                raise ValueError(f'cell {cell.name!r} references {slot!r} outside the captured batch')
    return BoundRecipe(recipe, snapshot)
