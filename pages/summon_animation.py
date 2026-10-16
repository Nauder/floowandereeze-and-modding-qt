"""Card-first GIF/MP4/PNG summon replacement using the application's configuration."""

import json
from pathlib import Path

from PIL import Image
from PySide6 import QtCore, QtWidgets

from database.models import SummonAnimationAssetModel, SummonAnimationEditModel
from database.objects import DBsession, session
from pages.models.summon_animation_model import SummonAnimationModel
from pages.ui.summon_animation import Ui_SummonAnimation
from services.summon_animation_service import Installation, SummonAnimationService
from unity.summon_metadata import component_dict
from unity.summon_frames import ImportMemoryWarning
from util.constants import APP_CONFIG
from widgets.summon_frames_editor import SummonFramesEditor
from widgets.ux import set_button_roles


class _Worker(QtCore.QThread):
    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    memory_warning = QtCore.Signal(str)

    def __init__(self, callback, parent):
        super().__init__(parent)
        self.callback = callback

    def run(self):
        try:
            self.completed.emit(self.callback())
        except ImportMemoryWarning as warning:
            self.memory_warning.emit(str(warning))
        except Exception as error:
            self.failed.emit(str(error))


class SummonAnimation(QtWidgets.QWidget, Ui_SummonAnimation):
    """Choose the card and source; resolve its region, quality and assets internally."""

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self._worker = None
        self._editor_key = None
        self._config_key = None
        self._last_result = None
        self.verticalLayout.setSpacing(10)
        self.verticalLayout.setStretch(3, 1)
        self.title.setStyleSheet("font-size: 24px; font-weight: 600;")
        for label in (self.title, self.notice, self.configurationSummary, self.status):
            label.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Maximum,
            )
        self.replacementLayout.setStretch(3, 1)
        self.configurationLayout.setStretch(0, 1)
        self.refreshButton.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.rows = []
        self.selected_rows = []
        self.model = SummonAnimationModel(parent=self)
        self.cardsView.setModel(self.model)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([250, 750])
        self.splitter.setChildrenCollapsible(False)
        self.cardsView.setAcceptDrops(False)
        self.cardsView.viewport().setAcceptDrops(False)
        self.setAcceptDrops(True)
        self.editor = SummonFramesEditor(None, [], self)
        self.editorHostLayout.addWidget(self.editor)
        self.gifButton = self.editor.gif_button
        self.pngButton = self.editor.png_button
        self.editor.applied.connect(
            lambda result: self._changed(result, self.editor.service)
        )
        self.editor.busy_changed.connect(self._editor_busy)
        self.lowerQuality.setStyleSheet(
            "QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #8292aa; border-radius: 2px; background: #111721; } QCheckBox::indicator:checked { background: #15a06f; border-color: #15a06f; }"
        )
        self.cardTitle.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.refreshButton.clicked.connect(self.refresh)
        self.search.textChanged.connect(self._filter)
        self.cardsView.selectionModel().currentChanged.connect(self._card_changed)
        self.lowerQuality.toggled.connect(self._quality_changed)
        self.restoreButton.clicked.connect(self._restore)
        set_button_roles(self)
        # Let drops over search, preview and settings reach the tab itself.
        for child in self.findChildren(QtWidgets.QWidget):
            child.setAcceptDrops(False)
        self._sync_configuration()
        self.refresh()

    def _configuration(self):
        region = (APP_CONFIG.asset_region or "tcg").lower()
        if region not in {"tcg", "ocg"}:
            raise ValueError("Choose TCG/Global or OCG in Configuration.")
        return APP_CONFIG.game_path, region

    def _sync_configuration(self):
        key = (*self._configuration(), APP_CONFIG.packer)
        if key == self._config_key or self.is_busy():
            return
        self._config_key = key
        label = "OCG" if key[1] == "ocg" else "Global / TCG"
        self.configurationSummary.setText(
            f"{label} · Using the game path from Configuration"
            if key[0]
            else f"{label} · Set your game path in Configuration first"
        )
        self._filter()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_configuration()

    def hideEvent(self, event):
        self.editor.pause()
        super().hideEvent(event)

    def closeEvent(self, event):
        if self.is_busy():
            event.ignore()
            self.status.setText(
                "Wait for the animation operation to finish before closing."
            )
            return
        self.editor.pause()
        super().closeEvent(event)

    def _service(self):
        game_path, asset_region = self._configuration()
        if not game_path:
            raise ValueError("Set your game path in Configuration first.")
        player = Path(game_path).resolve()
        # Configuration stores the LocalData player folder.
        game_root = player.parent.parent
        streaming = game_root / "masterduel_Data" / "StreamingAssets" / "AssetBundle"
        installation = Installation(
            "ocg" if asset_region == "ocg" else "global",
            player / "0000",
            streaming if streaming.is_dir() else None,
        )
        return SummonAnimationService(
            installation, self.rows, APP_CONFIG.packer or "lz4"
        )

    def _start(self, callback, success):
        if self.is_busy():
            return
        self.setEnabled(False)
        self.status.setText("Working…")
        self._worker = _Worker(callback, self)
        self._worker.completed.connect(success)
        self._worker.failed.connect(self._error)
        self._worker.finished.connect(self._finished)
        self._worker.start()

    def _finished(self):
        worker = self._worker
        self._worker = None
        self.setEnabled(True)
        self._buttons()
        self._sync_editor()
        if worker:
            worker.deleteLater()

    def _error(self, message):
        self.status.setText("Animation operation failed: " + message)

    def refresh(self):
        """Read metadata in a separate worker-owned database session."""
        self._sync_configuration()

        def read():
            with DBsession() as database:
                return [
                    component_dict(row)
                    for row in database.query(SummonAnimationAssetModel).all()
                ]

        self._start(read, self._loaded)

    def _loaded(self, rows):
        self.rows = rows
        self._filter()
        self.status.setText(
            "Select a card, then choose a GIF, MP4 or PNG frames."
            if rows
            else "Summon metadata is unavailable. Refresh data in Configuration."
        )

    def _filter(self, *_):
        self.selected_rows = []
        region = self._configuration()[1]
        game_region = "ocg" if region == "ocg" else "global"
        self.model.rows = [
            r
            for r in self.rows
            if r["game_region"] == game_region
            and r["asset_region"] in {region, "common"}
        ]
        self.model.filter(self.search.text(), game_region)
        self._card_changed()

    def _card_changed(self, *_):
        key = self.model.data(
            self.cardsView.currentIndex(), QtCore.Qt.ItemDataRole.UserRole
        )
        candidates = (
            [r for r in self.model.rows if (r["game_region"], r["card_id"]) == key]
            if key
            else []
        )
        preferred = self._configuration()[1]
        available = {
            r["asset_region"] for r in candidates if r["role"] == "skeleton_json"
        }
        region = (
            preferred
            if preferred in available
            else "common" if "common" in available else None
        )
        self.selected_rows = (
            [r for r in candidates if r["asset_region"] == region] if region else []
        )
        self.cardTitle.setText(
            candidates[0]["display_name"] or f"Card {key[1]}"
            if candidates
            else "Select a card"
        )
        self._quality_changed()

    def _quality_changed(self, *_):
        low = self.lowerQuality.isChecked()
        ready = any(
            r["role"] == "skeleton_json" and (r["quality"] == "sd") == low
            for r in self.selected_rows
        )
        self.qualityHint.setText(
            ("Lower quality selected." if low else "High quality selected.")
            if ready or not self.selected_rows
            else "This quality is unavailable for this card. Choose the other quality."
        )
        self._buttons()
        self._sync_editor()

    def _buttons(self):
        low = self.lowerQuality.isChecked()
        ready = bool(self._configuration()[0]) and any(
            r["role"] == "skeleton_json" and (r["quality"] == "sd") == low
            for r in self.selected_rows
        )
        self.gifButton.setEnabled(ready)
        self.pngButton.setEnabled(ready)
        self.restoreButton.setEnabled(
            bool(self.selected_rows and self._configuration()[0])
        )

    @staticmethod
    def _drop_source(mime):
        """Accept one local GIF/MP4 or a directory containing PNG frames."""
        urls = mime.urls() if mime.hasUrls() else []
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = Path(urls[0].toLocalFile())
        try:
            # Video validation/decoding belongs in the background preview worker.
            if path.is_file() and path.suffix.lower() == ".mp4":
                return str(path)
            if path.is_file() and path.suffix.lower() == ".gif":
                with Image.open(path) as image:
                    return str(path) if image.format == "GIF" else None
            if path.is_dir() and any(
                child.is_file() and child.suffix.lower() == ".png"
                for child in path.iterdir()
            ):
                return str(path)
        except OSError:
            pass
        return None

    def dragEnterEvent(self, event):
        if not self.is_busy() and self._drop_source(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        source = self._drop_source(event.mimeData())
        if source and not self.is_busy():
            self._import_frames(source)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _sync_editor(self):
        key = (
            self._configuration(),
            APP_CONFIG.packer,
            self.rows,
            self.selected_rows,
            self.lowerQuality.isChecked(),
        )
        if key == self._editor_key or self.is_busy():
            return
        self._editor_key = key
        service = None
        if (
            self.selected_rows
            and self._configuration()[0]
            and self.gifButton.isEnabled()
        ):
            try:
                service = self._service()
            except (ValueError, OSError) as error:
                self._error(str(error))
        self.editor.set_target(
            service,
            self.selected_rows if service else [],
            self.cardTitle.text(),
            self.lowerQuality.isChecked(),
        )

    def _editor_busy(self, busy):
        for widget in (
            self.cardsView,
            self.search,
            self.lowerQuality,
            self.refreshButton,
            self.restoreButton,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self._sync_configuration()
            self._buttons()

    def _import_frames(self, source):
        if not self.is_busy():
            self._sync_editor()
            self.editor.use_source(source)

    def is_busy(self):
        return self._worker is not None or self.editor.worker is not None

    def _changed(self, result, service=None):
        self._last_result = result
        if not result["modified"]:
            self.editor.invalidate()
        service = service or self._service()
        try:
            for path in result["manifests"]:
                manifest = json.loads(Path(path).read_text(encoding="utf-8"))
                relative = manifest["source"] + ":" + manifest["relative_path"]
                edit = (
                    session.query(SummonAnimationEditModel)
                    .filter_by(
                        installation=service.installation.key, relative_path=relative
                    )
                    .one_or_none()
                )
                if edit is None:
                    edit = SummonAnimationEditModel(
                        installation=service.installation.key,
                        relative_path=relative,
                        manifest=path,
                    )
                    session.add(edit)
                edit.modified = result["modified"]
            session.commit()
            self.status.setText(
                "Animation replaced. Originals are available for restoration."
                if result["modified"]
                else "Original animation restored."
            )
        except Exception as error:
            session.rollback()
            self._error(f"Files changed, but local state could not be saved: {error}")

    def _restore(self):
        try:
            service, rows = self._service(), list(self.selected_rows)
            self._start(
                service.backup_inventory,
                lambda entries: self._restore_ready(service, rows, entries),
            )
        except (ValueError, OSError) as error:
            self._error(str(error))

    def _restore_ready(self, service, rows, entries):
        QtCore.QTimer.singleShot(0, lambda: self._restore_card(service, rows, entries))

    def _restore_card(self, service, rows, entries):
        if self._worker is not None:
            QtCore.QTimer.singleShot(
                10, lambda: self._restore_card(service, rows, entries)
            )
            return
        identities = {(r["game_region"], r["card_id"], r["asset_region"]) for r in rows}
        matching = [
            e
            for e in entries
            if e.get("manifest")
            and any(
                (r["game_region"], r["card_id"], r["asset_region"]) in identities
                for r in e["manifest"]["components"]
            )
        ]
        if not matching:
            self.status.setText("No original backup is available for this card.")
            return
        other_cards = {
            r["card_id"]
            for e in matching
            for r in e["manifest"]["components"]
            if r["card_id"] is not None
            and (r["game_region"], r["card_id"], r["asset_region"]) not in identities
        }
        message = f"Close Master Duel first. Restore the original animation for {self.cardTitle.text()}?\nBoth quality versions will return to their original state."
        if other_cards:
            message += "\nShared files also restore these card IDs: " + ", ".join(
                sorted(other_cards)
            )
        if (
            QtWidgets.QMessageBox.question(
                self,
                "Restore original animation",
                message,
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return
        paths = [e["path"] for e in matching]
        self._start(
            lambda: service.restore_component_set(manifests=paths),
            lambda result: self._changed(result, service),
        )
