import math
import unicodedata
from enum import IntEnum


class Rarity(IntEnum):
    Common = 0
    Uncommon = 1
    Rare = 2
    Promo = 3
    Holo = 4
    Special = 5
    SIR = 6
    Mythical = 7


ODDS = (0.48, 0.25, 0.15, 0.02, 0.075, 0.02, 0.004, 0.001)
GOD_CHANCE = 0.01
ENERGY_CAP = 3
ENERGY_SECONDS = 7200
LANES = {
    "express": (200, 21600),
    "fast": (120, 86400),
    "standard": (70, 259200),
    "economy": (30, 432000),
}
CONDITIONS = ("Damaged", "Played", "Good", "Excellent", "Near Mint", "Mint", "Pristine")


def validate_rules():
    if len(ODDS) != len(Rarity) or any(w < 0 for w in ODDS) or not math.isclose(sum(ODDS), 1):
        raise ValueError("Pack rarity weights must sum to one")
    if not 0 <= GOD_CHANCE <= 1:
        raise ValueError("Invalid God Pack probability")


def normalize(value):
    return unicodedata.normalize("NFKC", value).casefold().strip()


def rarity(value):
    value = normalize(value or "")
    if "mythical" in value:
        return Rarity.Mythical
    if "special illustration" in value or value == "sir":
        return Rarity.SIR
    if any(x in value for x in ("secret", "ultra", "illustration", "special", "hyper")):
        return Rarity.Special
    if "holo" in value or "radiant" in value:
        return Rarity.Holo
    if "promo" in value:
        return Rarity.Promo
    if "rare" in value:
        return Rarity.Rare
    if "uncommon" in value:
        return Rarity.Uncommon
    return Rarity.Common


def condition(score):
    return CONDITIONS[min(6, max(0, score) * 7 // 101)]


def energy(value, updated, now):
    if value >= ENERGY_CAP:
        return value, now
    steps = max(0, now - updated) // ENERGY_SECONDS
    value = min(ENERGY_CAP, value + steps)
    return value, now if value == ENERGY_CAP else updated + steps * ENERGY_SECONDS


def roll_pack(rng, available, guaranteed=False, boosted=False):
    god = rng.random() < GOD_CHANCE
    high = [r for r in available if r >= Rarity.Holo]
    if not available or ((god or guaranteed) and not high):
        raise ValueError("Set must contain Holo-or-higher cards for guaranteed packs")
    weights = [ODDS[r] * (2 if boosted and r >= Rarity.Holo else 1) for r in available]
    rolled = rng.choices(available, weights=weights, k=5)
    if god:
        rolled = rng.choices(high, weights=[ODDS[r] for r in high], k=5)
    elif guaranteed:
        rolled[-1] = rng.choice(high)
    return rolled, god


def subgrades(rng, score):
    grades = [
        max(1.0, min(10.0, round((1 + score * 0.09 + rng.uniform(-1, 1)) * 2) / 2))
        for _ in range(4)
    ]
    return grades, round(sum(grades) / 4 * 2) / 2


def level_for(xp):
    return min(50, math.isqrt(max(0, xp) // 100) + 1)
