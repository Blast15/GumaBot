from .errors import DomainError


def blackjack_total(hand):
    total = sum(min(c, 10) if c != 1 else 11 for c in hand)
    for _ in range(hand.count(1)):
        if total > 21:
            total -= 10
    return total


def duel_step(state, actor, action, rng):
    if action not in ("attack", "defend", "heal", "rarity"):
        raise DomainError("Choose attack, defend, heal or rarity.")
    if state["turn"] % 2 != actor or state.get("winner") is not None:
        raise DomainError("It is not your turn.")
    other = 1 - actor
    fighters = state["fighters"]
    if action == "heal":
        if fighters[actor]["heals"] <= 0:
            raise DomainError("No heals left.")
        fighters[actor]["hp"] = min(100, fighters[actor]["hp"] + 18)
        fighters[actor]["heals"] -= 1
    elif action == "defend":
        fighters[actor]["shield"] = True
    else:
        damage = 12 + rng.randint(0, 6) + fighters[actor]["power"]
        if action == "rarity":
            if fighters[actor]["special"] <= 0:
                raise DomainError("Rarity move already used.")
            fighters[actor]["special"] -= 1
            damage += 10
        if fighters[other]["shield"]:
            damage //= 2
            fighters[other]["shield"] = False
        fighters[other]["hp"] = max(0, fighters[other]["hp"] - damage)
    state["turn"] += 1
    if fighters[other]["hp"] == 0:
        state["winner"] = actor
    elif state["turn"] >= 60:
        state["winner"] = 0 if fighters[0]["hp"] >= fighters[1]["hp"] else 1
    return state


def duel_state(powers):
    return {
        "turn": 0,
        "winner": None,
        "fighters": [
            {"hp": 100, "power": p, "shield": False, "heals": 2, "special": 1} for p in powers
        ],
    }


GYMS = (
    ("Mira", "Meadow", "Leafspark"),
    ("Orin", "Stone", "Quartz"),
    ("Sela", "Tide", "Seaglass"),
    ("Tavi", "Ember", "Cinder"),
    ("Neri", "Wind", "Gale"),
    ("Voss", "Frost", "Aurora"),
    ("Iona", "Light", "Prism"),
    ("Rook", "Night", "Eclipse"),
)
QUESTIONS = (
    ("How many cards are in a GumaBot pack?", ["3", "5", "7"], 1),
    ("How many cards form a deck?", ["5", "10", "20"], 0),
    ("Which tier ranks above Holo?", ["Common", "Uncommon", "SIR"], 2),
    ("How many duplicates does fusion consume?", ["2", "3", "4"], 1),
    ("Which currency is used in the market?", ["Coins", "Energy", "XP"], 0),
    ("What is the natural energy cap?", ["1", "3", "10"], 1),
    ("Which condition is highest?", ["Played", "Good", "Pristine"], 2),
    ("How many subgrades does grading use?", ["2", "4", "6"], 1),
    ("What is GumaBot's maximum level?", ["25", "50", "100"], 1),
    ("How many original gyms are there?", ["4", "6", "8"], 2),
)
