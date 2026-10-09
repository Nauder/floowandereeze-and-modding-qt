"""Regression coverage for scoped regex previews and dialog validation."""

import os
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dialogs.card_mass_edit_dialog import CardMassEditDialog
from util.card_text import preview_regex_replacement


def make_card(card_id, name="HERO", description="HERO effect", **edits):
    return SimpleNamespace(
        id=card_id,
        bundle=str(card_id),
        name=name,
        description=description,
        modded_name=edits.get("modded_name"),
        modded_description=edits.get("modded_description"),
    )


class RegexPreviewTests(unittest.TestCase):
    def test_counts_changed_cards_and_fields_without_mutating(self):
        cards = [make_card(1), make_card(2, "Other", "Other effect")]
        changes = preview_regex_replacement(cards, "HERO", "Hero", True, True)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].replacements, 2)
        self.assertEqual(changes[0].fields["name"], ("HERO", "Hero"))
        self.assertIsNone(cards[0].modded_name)

    def test_uses_existing_edits_including_empty_text(self):
        card = make_card(1, modded_name="New HERO", modded_description="")
        changes = preview_regex_replacement([card], "HERO", "Hero", True, True)
        self.assertEqual(changes[0].fields, {"name": ("New HERO", "New Hero")})

    def test_field_selection_capture_groups_and_duplicates(self):
        card = make_card(1)
        changes = preview_regex_replacement(
            [card, card], r"(HERO)", r"Super \1", False, True
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].replacements, 1)
        self.assertEqual(
            changes[0].fields, {"description": ("HERO effect", "Super HERO effect")}
        )

    def test_empty_scopes_no_matches_and_identical_replacements(self):
        for cards, pattern, replacement in (
            ([], "HERO", "Hero"),
            ([make_card(1)], "missing", "Hero"),
            ([make_card(1)], "HERO", "HERO"),
        ):
            self.assertEqual(
                preview_regex_replacement(cards, pattern, replacement, True, True), []
            )

    def test_invalid_pattern_and_replacement_even_with_empty_scope(self):
        for pattern, replacement in (("[", ""), ("HERO", r"\2")):
            with self.assertRaises(re.error):
                preview_regex_replacement([], pattern, replacement, True, True)


class MassEditDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.card = make_card(1)
        self.dialog = CardMassEditDialog(
            scopes={"Selected cards": [self.card], "Favorites": []}
        )
        self.addCleanup(self.dialog.close)
        self.dialog.regex_input.setText("HERO")
        self.dialog.replacement_input.setText("Hero")

    def test_preview_counts_differences_and_invalidates_on_changes(self):
        self.assertFalse(self.dialog.apply_button.isEnabled())
        self.dialog._preview_replacement()
        self.assertIn("1 of 1 cards", self.dialog.summary.text())
        self.assertIn("2 replacement(s)", self.dialog.summary.text())
        self.assertIn("HERO", self.dialog.before_text.toPlainText())
        self.assertIn("Hero", self.dialog.after_text.toPlainText())
        self.assertIn("-HERO", self.dialog.diff_text.toPlainText())
        self.assertIn("+Hero", self.dialog.diff_text.toPlainText())
        self.assertTrue(self.dialog.apply_button.isEnabled())
        self.dialog.replacement_input.setText("Other")
        self.assertFalse(self.dialog.apply_button.isEnabled())
        self.assertEqual(self.dialog.diff_text.toPlainText(), "")

    def test_empty_scope_cannot_apply(self):
        self.dialog._preview_replacement()
        self.dialog.scope_input.setCurrentIndex(1)
        self.assertFalse(self.dialog.apply_button.isEnabled())
        self.dialog._preview_replacement()
        self.assertIn("0 of 0 cards", self.dialog.summary.text())
        self.dialog._accept_replacement()
        self.assertEqual(self.dialog.result(), 0)

    def test_bad_replacement_stays_open(self):
        self.dialog.replacement_input.setText(r"\2")
        with patch.object(self.dialog, "_show_error") as warning:
            self.dialog._preview_replacement()
        warning.assert_called_once()
        self.assertFalse(self.dialog.apply_button.isEnabled())

    def test_diff_shows_trailing_newline_changes(self):
        self.dialog.replacement_input.setText(r"HERO\n")
        self.dialog._preview_replacement()
        self.assertIn("-HERO", self.dialog.diff_text.toPlainText())
        self.assertIn("+HERO", self.dialog.diff_text.toPlainText())
        self.assertIn("No newline", self.dialog.diff_text.toPlainText())


if __name__ == "__main__":
    unittest.main()
