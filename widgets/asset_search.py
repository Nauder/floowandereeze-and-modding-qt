"""Card art style search controls for named accessory editors."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QCompleter, QLabel, QLineEdit, QPushButton
from pyqttoast import ToastPreset

from util.ui_util import show_toast


def add_asset_search(page, header, results_layout, asset_type):
    """Add explicit search, completion, and inline minimum-length guidance."""
    page.searchEdit = QLineEdit(page)
    page.searchEdit.setObjectName("searchEdit")
    page.searchEdit.setPlaceholderText(f"Search {asset_type}, min 3 characters")
    page.searchEdit.setMinimumHeight(32)
    page.searchEdit.setStyleSheet("color: #ffffff;")
    palette = page.searchEdit.palette()
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#858585"))
    page.searchEdit.setPalette(palette)
    page.searchEdit.setClearButtonEnabled(True)
    page.searchButton = QPushButton(page)
    page.searchButton.setObjectName("searchButton")
    page.searchButton.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.EditFind))
    page.searchButton.setToolTip("Search")
    page.searchButton.setAccessibleName("Search")
    page.searchButton.setCursor(Qt.CursorShape.PointingHandCursor)
    page.searchButton.setMinimumHeight(32)
    if page.searchButton.icon().isNull():
        page.searchButton.setText("Search")
        page.searchButton.setMaximumWidth(70)
    else:
        page.searchButton.setMaximumWidth(42)
    header.insertWidget(1, page.searchEdit, 1)
    header.insertWidget(2, page.searchButton)
    page.searchHelperLabel = QLabel("", page)
    page.searchHelperLabel.setObjectName("searchHelperLabel")
    page.searchHelperLabel.setStyleSheet("color: #d6d6d6; font-size: 11px;")
    results_layout.addWidget(page.searchHelperLabel)

    completer = QCompleter(page.model.get_names(), page)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    page.searchEdit.setCompleter(completer)

    def search(*_):
        if page.model.show_favorites:
            return
        text = page.searchEdit.text()
        if text and len(text) < 3:
            page.searchHelperLabel.setText("Enter at least 3 characters to search.")
            show_toast(
                page,
                "Search",
                "Please use 3 or more characters to search",
                ToastPreset.INFORMATION_DARK,
            )
            return
        page.searchHelperLabel.clear()
        page.model.filter = text
        page.model.refresh()
        page.model.layoutChanged.emit()

    page.searchButton.clicked.connect(search)
    page.searchEdit.returnPressed.connect(search)
    completer.activated.connect(search)

    def text_changed(text):
        page.searchHelperLabel.clear()
        if not text:
            page.model.filter = ""
            search()

    page.searchEdit.textChanged.connect(text_changed)
