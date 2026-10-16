import difflib
import re

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from util.card_text import preview_regex_replacement


class DiffHighlighter(QSyntaxHighlighter):
    """Give unified diff lines distinct colors in light and dark themes."""

    def __init__(self, document, palette):
        super().__init__(document)
        dark = palette.color(QPalette.ColorRole.Base).lightness() < 128
        self.removed = QTextCharFormat()
        self.removed.setForeground(QColor("#ffb4b4" if dark else "#9c2525"))
        self.removed.setBackground(QColor("#48282e" if dark else "#ffebe9"))
        self.added = QTextCharFormat()
        self.added.setForeground(QColor("#b7efc5" if dark else "#116329"))
        self.added.setBackground(QColor("#203c2e" if dark else "#dafbe1"))
        self.header = QTextCharFormat()
        self.header.setForeground(QColor("#9ecbff" if dark else "#0550ae"))
        self.header.setFontWeight(QFont.Weight.Bold)
        self.note = QTextCharFormat()
        self.note.setForeground(palette.color(QPalette.ColorRole.PlaceholderText))
        self.note.setFontItalic(True)

    def highlightBlock(self, text):
        """Style headers before interpreting addition/removal prefixes."""
        if text.startswith(("--- ", "+++ ", "@@")):
            text_format = self.header
        elif text.startswith("-"):
            text_format = self.removed
        elif text.startswith("+"):
            text_format = self.added
        elif text.startswith("\\"):
            text_format = self.note
        else:
            return
        self.setFormat(0, len(text), text_format)


class CardMassEditDialog(QDialog):
    """Preview a regex replacement within a chosen set of cards."""

    def __init__(self, parent=None, scopes=None):
        super().__init__(parent)
        self.scopes = scopes or {"All cards": []}
        self.changes = []
        self.setWindowTitle("Mass Edit Card Text")
        self.setModal(True)
        self.resize(900, 650)

        icon = QIcon()
        icon.addFile(
            ":/ui/images/icon.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off
        )
        self.setWindowIcon(icon)

        layout = QVBoxLayout(self)
        self.scope_input = QComboBox()
        for label, cards in self.scopes.items():
            self.scope_input.addItem(f"{label} ({len(cards)} cards)", label)
        scope_layout = QFormLayout()
        scope_layout.addRow("Apply to:", self.scope_input)
        layout.addLayout(scope_layout)
        hint = QLabel(
            "Selected cards uses Ctrl/Shift selection in the card list. "
            "Search results uses the currently displayed search; "
            "favorites includes every favorite in the current region."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        regex_group = QGroupBox("Regex find and replace")
        regex_layout = QFormLayout(regex_group)
        self.regex_input = QLineEdit()
        self.regex_input.setPlaceholderText("Regex to find")
        self.regex_input.setToolTip(
            "Python regular expression. For example: "
            "(?:Destiny|Elemental|Evil|Vision)\\s+HERO"
        )
        self.replacement_input = QLineEdit()
        self.replacement_input.setPlaceholderText("Replacement text")
        self.replacement_input.setToolTip(
            "Replacement text. Capture groups such as \\1 are supported."
        )
        self.names_checkbox = QCheckBox("Names")
        self.names_checkbox.setChecked(True)
        self.descriptions_checkbox = QCheckBox("Descriptions")
        self.descriptions_checkbox.setChecked(True)
        fields_layout = QHBoxLayout()
        fields_layout.addWidget(self.names_checkbox)
        fields_layout.addWidget(self.descriptions_checkbox)
        fields_layout.addStretch()

        regex_layout.addRow("Find:", self.regex_input)
        regex_layout.addRow("Replace with:", self.replacement_input)
        regex_layout.addRow("Text fields:", fields_layout)
        layout.addWidget(regex_group)

        self.summary = QLabel("Preview the replacement to see affected cards.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.card_input = QComboBox()
        self.card_input.currentIndexChanged.connect(self._show_change)
        layout.addWidget(self.card_input)
        previews = QSplitter()
        self.before_text = QPlainTextEdit()
        self.after_text = QPlainTextEdit()
        for title, editor in (("Before", self.before_text), ("After", self.after_text)):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.addWidget(QLabel(title))
            editor.setReadOnly(True)
            panel_layout.addWidget(editor)
            previews.addWidget(panel)
        layout.addWidget(previews, 1)
        self.diff_text = QPlainTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_highlighter = DiffHighlighter(
            self.diff_text.document(), self.diff_text.palette()
        )
        layout.addWidget(QLabel("Differences (- removed in red, + added in green)"))
        layout.addWidget(self.diff_text, 1)

        buttons = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        preview_button = QPushButton("Preview Changes")
        preview_button.clicked.connect(self._preview_replacement)
        self.apply_button = QPushButton("Apply Changes")
        self.apply_button.setEnabled(False)
        cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self._accept_replacement)
        buttons.addWidget(cancel_button)
        buttons.addWidget(preview_button)
        buttons.addWidget(self.apply_button)
        layout.addLayout(buttons)

        self.regex_input.textChanged.connect(self._invalidate_preview)
        self.replacement_input.textChanged.connect(self._invalidate_preview)
        self.names_checkbox.toggled.connect(self._invalidate_preview)
        self.descriptions_checkbox.toggled.connect(self._invalidate_preview)
        self.scope_input.currentIndexChanged.connect(self._invalidate_preview)

    def get_inputs(self):
        """Return the regex replacement and selected text fields."""
        return (
            self.regex_input.text(),
            self.replacement_input.text(),
            self.names_checkbox.isChecked(),
            self.descriptions_checkbox.isChecked(),
        )

    def get_cards(self):
        """Return the explicit scope, including an empty scope."""
        return self.scopes[self.scope_input.currentData()]

    def _invalidate_preview(self, *_):
        self.changes = []
        self.card_input.clear()
        self.before_text.clear()
        self.after_text.clear()
        self.diff_text.clear()
        self.apply_button.setEnabled(False)
        self.summary.setText("Preview the replacement to see affected cards.")

    def _preview_replacement(self):
        """Validate and compute changes without writing any files."""
        self._invalidate_preview()
        pattern, replacement, names, descriptions = self.get_inputs()

        if not pattern:
            self._show_error("Enter a regular expression to find.")
            return
        if not names and not descriptions:
            self._show_error("Select at least one text field to replace.")
            return

        try:
            self.changes = preview_regex_replacement(
                self.get_cards(), pattern, replacement, names, descriptions
            )
        except (re.error, IndexError) as error:
            self._show_error(f"Invalid regex or replacement: {error}")
            return

        replacements = sum(change.replacements for change in self.changes)
        self.summary.setText(
            f"{len(self.changes)} of {len(self.get_cards())} cards will change; "
            f"{replacements} replacement(s)."
        )
        for change in self.changes:
            self.card_input.addItem(f"{change.card.name} ({change.card.bundle})")
        self.apply_button.setEnabled(bool(self.changes))

    def _show_change(self, index):
        if index < 0 or index >= len(self.changes):
            return
        fields = self.changes[index].fields
        self.before_text.setPlainText(
            "\n\n".join(
                f"{field.title()}:\n{before}" for field, (before, _) in fields.items()
            )
        )
        self.after_text.setPlainText(
            "\n\n".join(
                f"{field.title()}:\n{after}" for field, (_, after) in fields.items()
            )
        )
        differences = []
        for field, (before, after) in fields.items():
            for line in difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"{field} before",
                tofile=f"{field} after",
            ):
                differences.append(line)
                if not line.endswith("\n"):
                    differences.append("\n\\ No newline at end of text\n")
        self.diff_text.setPlainText("".join(differences))

    def _accept_replacement(self):
        """Only accept a previewed replacement that changes text."""
        if self.changes and self.apply_button.isEnabled():
            self.accept()

    def _show_error(self, message):
        """Show a validation error without closing the dialog."""
        QMessageBox.warning(self, "Mass edit", message)
