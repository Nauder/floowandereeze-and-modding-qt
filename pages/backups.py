"""Backup inventory and scoped archive import/export UI."""

import logging
from zipfile import BadZipFile

from PySide6 import QtCore, QtWidgets
from sqlalchemy.exc import SQLAlchemyError

from services.backup_service import BackupService, CATEGORY_LABELS, sync_backup_flags
from widgets.ux import set_button_roles

logger = logging.getLogger(__name__)

PICKER_STYLE = """
    QTableWidget, QComboBox {
        background-color: rgba(12, 12, 12, 0.7);
        color: white;
        border: 1px solid #2f2f2f;
        border-radius: 5px;
    }
    QTableWidget {
        gridline-color: rgba(255, 255, 255, 0.08);
        selection-background-color: rgba(21, 160, 111, 0.24);
        selection-color: white;
    }
    QTableWidget::item {
        padding: 4px;
        border: 1px solid transparent;
    }
    QTableWidget::item:selected {
        background-color: rgba(21, 160, 111, 0.24);
        border: 1px solid #15a06f;
    }
    QHeaderView {
        background-color: transparent;
    }
    QHeaderView::section, QTableCornerButton::section {
        background-color: rgba(12, 12, 12, 0.7);
        color: white;
        border: none;
        border-bottom: 1px solid #2f2f2f;
        padding: 5px;
    }
    QComboBox {
        padding: 4px 24px 4px 8px;
    }
    QComboBox:hover, QComboBox:focus {
        border-color: #15a06f;
    }
    QComboBox QAbstractItemView {
        background-color: rgba(12, 12, 12, 0.7);
        color: white;
        border: 1px solid #454545;
        selection-background-color: rgba(21, 160, 111, 0.24);
        selection-color: white;
    }
    QScrollBar {
        background-color: rgba(12, 12, 12, 0.7);
        border: none;
    }
    QScrollBar::handle {
        background-color: rgba(255, 255, 255, 0.25);
        border-radius: 4px;
        min-width: 20px;
        min-height: 20px;
    }
    QScrollBar::handle:hover {
        background-color: rgba(255, 255, 255, 0.4);
    }
    QScrollBar::add-page, QScrollBar::sub-page {
        background-color: transparent;
    }
"""


class BackupPicker(QtWidgets.QWidget):
    """Use the same scope and selection controls for local and archive files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PICKER_STYLE)
        self.entries = []
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("Category:"))
        self.category = QtWidgets.QComboBox()
        controls.addWidget(self.category)
        controls.addWidget(QtWidgets.QLabel("Action scope:"))
        self.scope = QtWidgets.QComboBox()
        self.scope.addItems(["Everything", "Current category", "Selected backups"])
        controls.addWidget(self.scope)
        controls.addStretch()
        layout.addLayout(controls)
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Category", "Backup file", "Size (KiB)"])
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        for column in (0, 2):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.verticalHeader().hide()
        layout.addWidget(self.table)
        self.summary = QtWidgets.QLabel()
        layout.addWidget(self.summary)
        layout.addWidget(
            QtWidgets.QLabel(
                "Use Ctrl or Shift to select multiple rows. "
                "Everything includes hidden categories."
            )
        )
        self.category.currentIndexChanged.connect(self._filter)
        self.scope.currentIndexChanged.connect(self._update_summary)
        self.table.itemSelectionChanged.connect(self._update_summary)

    def set_entries(self, entries):
        """Replace the inventory while retaining the category filter."""
        previous = self.category.currentData()
        self.entries = entries
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("All categories", None)
        for category in sorted({entry.category for entry in entries}):
            self.category.addItem(CATEGORY_LABELS.get(category, category), category)
        index = self.category.findData(previous)
        self.category.setCurrentIndex(max(0, index))
        self.category.blockSignals(False)
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            for column, value in enumerate(
                (
                    CATEGORY_LABELS.get(entry.category, entry.category),
                    entry.name,
                    f"{entry.size / 1024:,.1f}",
                )
            ):
                self.table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        self._filter()

    def _filter(self):
        category = self.category.currentData()
        self.table.clearSelection()
        for row, entry in enumerate(self.entries):
            self.table.setRowHidden(
                row, category is not None and entry.category != category
            )
        self._update_summary()

    def names(self):
        """Return the files targeted by the explicitly selected scope."""
        scope = self.scope.currentIndex()
        if scope == 0:
            return [entry.name for entry in self.entries]
        if scope == 1:
            category = self.category.currentData()
            return [entry.name for entry in self.entries if entry.category == category]
        return [
            self.entries[index.row()].name
            for index in self.table.selectionModel().selectedRows()
            if index.row() < len(self.entries)
            and not self.table.isRowHidden(index.row())
        ]

    def _update_summary(self):
        self.summary.setText(
            f"{len(self.entries)} backups available · {len(self.names())} in action scope"
        )


class Backups(QtWidgets.QWidget):
    """Manage backups without requiring a configured game installation."""

    def __init__(self, service=None):
        super().__init__()
        self.service = service or BackupService()
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Backups")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(
            QtWidgets.QLabel(
                "Manage saved originals. Importing or removing backups "
                "does not change game files."
            )
        )
        self.picker = BackupPicker(self)
        layout.addWidget(self.picker)
        actions = QtWidgets.QHBoxLayout()
        for text, name, callback in (
            ("Refresh", "refreshButton", self.refresh),
            ("Export ZIP…", "exportButton", self._export),
            ("Import ZIP…", "importButton", self._import),
            ("Remove backups…", "clearButton", self._delete),
        ):
            button = QtWidgets.QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        set_button_roles(self)
        self.refresh()

    def showEvent(self, event):
        """Refresh files whenever the user opens this tab."""
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        """Rescan the backup folder."""
        try:
            self.picker.set_entries(self.service.inventory())
        except (OSError, ValueError) as error:
            self._error(error)

    def _error(self, error):
        logger.error("Backup operation failed: %s", error)
        self.status.setText(f"Backup operation failed: {error}")
        QtWidgets.QMessageBox.warning(self, "Backups", str(error))

    def _names(self):
        names = self.picker.names()
        if not names:
            QtWidgets.QMessageBox.information(
                self,
                "Backups",
                "Choose a category or select backups for this action.",
            )
        return names

    def _changed(self):
        self.refresh()
        try:
            sync_backup_flags(self.service)
        except (OSError, ValueError, SQLAlchemyError) as error:
            from database.objects import session

            session.rollback()
            self._error(
                f"Files changed, but backup indicators could not be updated: {error}"
            )
            return
        # ORM identities update in place; notify lists without reloading game textures.
        from pages.models.asset_list_model import AssetListModel

        for page in self.window().findChildren(QtWidgets.QWidget):
            model = getattr(page, "model", None)
            if not isinstance(model, AssetListModel):
                continue
            if model.rowCount(QtCore.QModelIndex()):
                model.dataChanged.emit(
                    model.index(0),
                    model.index(model.rowCount(QtCore.QModelIndex()) - 1),
                )

    def _export(self):
        names = self._names()
        if not names:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export backups", "floo-backups.zip", "ZIP archives (*.zip)"
        )
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        try:
            count = self.service.export_archive(path, names)
            self.status.setText(f"Exported {count} backups to {path}")
        except (OSError, ValueError, BadZipFile, RuntimeError) as error:
            self._error(error)

    def _delete(self):
        names = self._names()
        if not names:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Remove backups",
            f"Permanently remove {len(names)} backups? "
            "Export them first if you may need them again.",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            count = self.service.delete(names)
            self.status.setText(f"Removed {count} backups.")
        except (OSError, ValueError) as error:
            self._error(error)
        finally:
            self._changed()

    def _import(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import backups", "", "ZIP archives (*.zip)"
        )
        if not path:
            return
        try:
            entries = self.service.inspect_archive(path)
            if not entries:
                raise ValueError("This archive contains no backups.")
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("Choose backups to import")
            dialog.resize(850, 550)
            layout = QtWidgets.QVBoxLayout(dialog)
            picker = BackupPicker(dialog)
            picker.set_entries(entries)
            layout.addWidget(picker)
            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.StandardButton.Ok
                | QtWidgets.QDialogButtonBox.StandardButton.Cancel
            )
            buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(
                "Import"
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return
            names = picker.names()
            if not names:
                raise ValueError("Choose at least one backup to import.")
            existing = {entry.name.casefold() for entry in self.service.inventory()}
            conflicts = sum(name.casefold() in existing for name in names)
            overwrite = False
            if conflicts:
                answer = QtWidgets.QMessageBox.question(
                    self,
                    "Existing backups",
                    f"{conflicts} backups already exist. Replace them? "
                    "Choose No to keep them and import only new files.",
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No
                    | QtWidgets.QMessageBox.StandardButton.Cancel,
                    QtWidgets.QMessageBox.StandardButton.No,
                )
                if answer == QtWidgets.QMessageBox.StandardButton.Cancel:
                    return
                overwrite = answer == QtWidgets.QMessageBox.StandardButton.Yes
            try:
                count, skipped = self.service.import_archive(path, names, overwrite)
                self.status.setText(
                    f"Imported {count} backups; kept {skipped} existing backups."
                )
            finally:
                self._changed()
        except (OSError, ValueError, BadZipFile, RuntimeError) as error:
            self._error(error)
