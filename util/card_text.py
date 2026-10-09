"""Plan card text replacements without changing cards or game files."""

import re
from dataclasses import dataclass


@dataclass
class CardTextChange:
    """Before and after text for the changed fields of one card."""

    card: object
    fields: dict
    replacements: int


def preview_regex_replacement(
    cards, pattern, replacement, replace_names, replace_descriptions
):
    """Return actual text changes, using existing edits as the starting text."""
    regex = re.compile(pattern)
    # Validate replacement references even when the target set is empty.
    regex.sub(replacement, "")
    changes = []
    seen = set()
    for card in cards:
        if card.id in seen:
            continue
        seen.add(card.id)
        fields = {}
        replacements = 0
        for field, enabled in (
            ("name", replace_names),
            ("description", replace_descriptions),
        ):
            if not enabled:
                continue
            edited = getattr(card, f"modded_{field}")
            before = edited if edited is not None else getattr(card, field)
            after, count = regex.subn(replacement, before)
            if after != before:
                fields[field] = (before, after)
                replacements += count
        if fields:
            changes.append(CardTextChange(card, fields, replacements))
    return changes
