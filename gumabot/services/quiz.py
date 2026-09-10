"""Quiz snapshots survive catalog refreshes and application restarts."""

import json
import random
from typing import Any

from .engines import QUESTIONS

Question = tuple[str, list[str], int]


def build_questions(rows: list[dict[str, Any]], rng: random.Random) -> list[Question]:
    facts = []
    for row in rows:
        try:
            data = json.loads(row["metadata"])
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        label = f"{row['name']} ({row['id']})"
        for field, title in (
            ("set_name", "set"),
            ("rarity", "rarity"),
            ("illustrator", "illustrator"),
            ("hp", "HP"),
        ):
            value = data.get(field)
            if value is not None and str(value).strip():
                facts.append((label, title, str(value)))
    # Construct distractors for ten sampled facts, rather than every catalog fact.
    values = {
        title: sorted({v for _, t, v in facts if t == title and len(v) <= 80})
        for title in {t for _, t, _ in facts}
    }
    eligible = [
        (label, title, answer)
        for label, title, answer in facts
        if len(answer) <= 80 and len(values[title]) >= 3
    ]
    selected = []
    for label, title, answer in rng.sample(eligible, min(10, len(eligible))):
        alternatives = [v for v in values[title] if v != answer]
        options = [answer, *rng.sample(alternatives, 2)]
        rng.shuffle(options)
        selected.append((f"What is the {title} of {label}?", options, options.index(answer)))
    if len(selected) < 10:
        selected.extend(rng.sample(list(QUESTIONS), 10 - len(selected)))
    rng.shuffle(selected)
    return selected


def question_at(state: dict[str, Any], position: int) -> Question:
    if "questions" in state:
        question, options, answer = state["questions"][position]
        return question, options, answer
    # Compatibility with sessions saved by releases before catalog quizzes.
    return QUESTIONS[state["order"][position]]
