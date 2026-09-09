import random
from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gumabot.services.engines import blackjack_total, duel_state, duel_step
from gumabot.services.errors import DomainError
from gumabot.services.rules import (
    GOD_CHANCE,
    ODDS,
    Rarity,
    condition,
    energy,
    level_for,
    normalize,
    rarity,
    roll_pack,
    subgrades,
    validate_rules,
)


@pytest.mark.parametrize(
    "elapsed,expected", [(0, 0), (7199, 0), (7200, 1), (14400, 2), (21600, 3), (86400, 3)]
)
def test_energy_boundaries(elapsed, expected):
    assert energy(0, 100, 100 + elapsed)[0] == expected


def test_energy_overflow_and_clock_reversal():
    assert energy(5, 0, 100) == (5, 100)
    assert energy(0, 100, 90) == (0, 100)
    assert energy(0, 100, 7301) == (1, 7300)


@given(st.integers(0, 100), st.integers(0, 100000))
def test_grade_bounds(score, seed):
    grades, final = subgrades(random.Random(seed), score)
    assert all(1 <= g <= 10 and g * 2 == int(g * 2) for g in grades + [final])
    assert condition(score)


@given(st.integers(0, 10**9))
def test_levels(xp):
    assert 1 <= level_for(xp) <= 50


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 0),
        ("Unknown future tier", 0),
        ("Uncommon", 1),
        ("Rare", 2),
        ("Promo", 3),
        ("Rare Holo", 4),
        ("Ultra Rare", 5),
        ("Special Illustration Rare", 6),
        ("Mythical", 7),
    ],
)
def test_rarity(value, expected):
    assert rarity(value) == expected


def test_normalization():
    assert normalize(" ＰＯＫÉＭＯＮ ") == normalize("Pokémon")


def test_simulation_100000_packs():
    validate_rules()
    rng = random.Random(20260909)
    gods = 0
    distribution = Counter()
    for _ in range(100000):
        ranks, god = roll_pack(rng, list(Rarity))
        assert len(ranks) == 5
        gods += god
        if god:
            assert min(ranks) >= Rarity.Holo
        else:
            distribution.update(ranks)
    assert abs(gods / 100000 - GOD_CHANCE) < 0.002
    total = sum(distribution.values())
    for rank, weight in enumerate(ODDS):
        assert abs(distribution[rank] / total - weight) < 0.004


def test_pack_guarantee_and_invalid_pool():
    for seed in range(20):
        ranks, _ = roll_pack(random.Random(seed), [0, 4], True, True)
        assert max(ranks) >= 4
    with pytest.raises(ValueError):
        roll_pack(random.Random(1), [], True)
    with pytest.raises(ValueError):
        roll_pack(random.Random(1), [0], True)


@pytest.mark.parametrize(
    "hand,total", [([1, 1, 9], 21), ([1, 13, 10], 21), ([13, 12, 5], 25), ([1, 1, 1, 1], 14)]
)
def test_blackjack_total(hand, total):
    assert blackjack_total(hand) == total


def test_duel_engine():
    state = duel_state([5, 2])
    rng = random.Random(1)
    with pytest.raises(DomainError):
        duel_step(state, 1, "attack", rng)
    with pytest.raises(DomainError):
        duel_step(state, 0, "invalid", rng)
    duel_step(state, 0, "defend", rng)
    duel_step(state, 1, "rarity", rng)
    duel_step(state, 0, "heal", rng)
    with pytest.raises(DomainError):
        duel_step(state, 1, "rarity", rng)
    while state["winner"] is None:
        duel_step(state, state["turn"] % 2, "attack", rng)
    assert state["winner"] in (0, 1)
