"""Fixed five-class order shared by dataset, detector, and docs."""

from __future__ import annotations

CLASS_NAMES: tuple[str, ...] = (
    "player",
    "enemy",
    "energy_orb",
    "treasure_chest",
    "health_potion",
)

CLASS_ID_BY_NAME: dict[str, int] = {
    name: index for index, name in enumerate(CLASS_NAMES)
}

EXPECTED_TRAIN_IMAGES = 96
EXPECTED_VAL_IMAGES = 24
EXPECTED_LABEL_COUNTS: dict[str, int] = {
    "player": 85,
    "enemy": 80,
    "energy_orb": 90,
    "treasure_chest": 86,
    "health_potion": 74,
}
