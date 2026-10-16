"""Capture documentation images from the real Qt window and local game assets.

Run with the project's Python environment; see docs/development/screenshots.md.
Application imports must stay inside capture(), after changing to the sandbox.
"""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    "config",
    "sleeve",
    "card",
    "card_icon",
    "face",
    "background",
    "icon",
    "field",
    "wallpaper",
    "coin",
    "deck_box",
    "summon-animation",
    "backups",
)


def arguments():
    """Keep capture choices explicit and reproducible."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "database.db")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs/assets/ui",
        help="PNG destination (default: docs/assets/ui; existing screenshots are replaced)",
    )
    parser.add_argument("--pages", nargs="+", choices=PAGES, default=PAGES)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Use --width and --height instead of maximizing to the desktop",
    )
    parser.add_argument("--card-search", default="Floowandereeze")
    parser.add_argument("--summon-search", default="Blue-Eyes White Dragon")
    parser.add_argument(
        "--summon-source",
        type=Path,
        help="Optional GIF/MP4 or PNG folder for a real prepared preview",
    )
    parser.add_argument(
        "--memory-warning",
        action="store_true",
        help="Also capture and cancel the real large-import warning using enlarged card artwork",
    )
    parser.add_argument(
        "--offscreen",
        action="store_true",
        help="Use Qt's offscreen platform instead of showing the window",
    )
    return parser.parse_args()


def capture(args, sandbox):
    """Load unchanged application widgets against a disposable database copy."""
    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # Fixed logical scale; Qt still captures at the screen's native pixel density.
    os.environ["QT_SCALE_FACTOR"] = "1"
    os.environ["TEMP"] = str(sandbox)
    os.environ["TMP"] = str(sandbox)
    sys.path.insert(0, str(ROOT))
    source_uri = args.database.as_uri() + "?mode=ro"
    print("Copying development database...", flush=True)
    with closing(sqlite3.connect(source_uri, uri=True)) as source:
        with closing(sqlite3.connect(sandbox / "database.db")) as destination:
            source.backup(destination)
    os.chdir(sandbox)
    print("Loading Qt and application modules...", flush=True)

    from PySide6 import QtCore, QtWidgets

    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    for scope in (QtCore.QSettings.Scope.UserScope, QtCore.QSettings.Scope.SystemScope):
        QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, scope, str(sandbox))
    app = QtWidgets.QApplication([])

    from util.constants import APP_CONFIG
    from util.python_utils import is_valid_game_path
    from util.ui_util import get_dark_mode_palette
    from database.objects import engine, session
    from pages.main_window import MainWindow
    from services.backup_service import BackupService
    from database.models import CardModel, CardOcgModel
    from unity.unity_utils import fetch_bundle_thumb
    from dialogs.card_mass_edit_dialog import CardMassEditDialog

    valid, _ = is_valid_game_path(APP_CONFIG.game_path or "")
    if not valid:
        raise RuntimeError(
            "The database must point to an available Master Duel installation."
        )
    # Use the shipped background, rather than a user's private custom image.
    APP_CONFIG.background_path = None
    app.setPalette(get_dark_mode_palette(app))
    splash = QtWidgets.QSplashScreen()
    window = None
    dialogs = []
    warning_expected = False
    warning_captured = False

    def dismiss_dialog():
        nonlocal warning_captured
        dialog = app.activeModalWidget()
        if isinstance(dialog, QtWidgets.QMessageBox):
            if warning_expected and dialog.windowTitle() == "Large animation import":
                save_capture(dialog, "summon-memory-warning.png", None)
                warning_captured = True
            else:
                dialogs.append(dialog.text())
            dialog.reject()

    guard = QtCore.QTimer()
    guard.timeout.connect(dismiss_dialog)
    guard.start(100)

    def settle(page=None, timeout=120):
        deadline = time.monotonic() + timeout
        while True:
            app.processEvents()
            time.sleep(0.02)  # Release the GIL for Python-backed Qt workers.
            if dialogs:
                dialogs.clear()
                raise RuntimeError("The app reported a dialog; capture aborted.")
            busy = page is not None and hasattr(page, "is_busy") and page.is_busy()
            if not busy:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("Timed out waiting for the app's worker.")
        # Finish queued splitter, layout and image resize updates.
        for _ in range(20):
            app.processEvents()
            time.sleep(0.02)

    manifest = {
        "window_mode": "windowed" if args.windowed or args.offscreen else "maximized",
        "platform": app.platformName(),
        "qt": QtCore.qVersion(),
        "captures": [],
        "notes": "Real application widgets and local assets; paths redacted in Configuration. "
        "Image previews reuse selected installed artwork; no replacement is applied.",
    }

    def save_capture(widget, filename, selected):
        screenshot = widget.grab()
        if not screenshot.save(str(args.output / filename)):
            raise RuntimeError(f"Cannot save {filename}.")
        details = {
            "file": filename,
            "selected": selected,
            "pixels": [screenshot.width(), screenshot.height()],
            "logical_size": [widget.width(), widget.height()],
        }
        if widget is window:
            page = window.mainStack.currentWidget()
            if hasattr(page, "RESULT_ITEM_SIZE"):
                view = page.findChild(QtWidgets.QListView)
                rows = {
                    view.visualRect(view.model().index(row, 0)).y()
                    for row in range(view.model().rowCount(QtCore.QModelIndex()))
                    if view.viewport()
                    .rect()
                    .contains(view.visualRect(view.model().index(row, 0)))
                }
                details["selector_full_rows"] = len(rows)
                if view.model().rowCount(QtCore.QModelIndex()) > 1 and len(rows) < 2:
                    raise RuntimeError(
                        f"Selector has fewer than two full rows: {filename}"
                    )
            if hasattr(page, "wallpaperView"):
                details["selector_width"] = page.wallpaperView.width()
        manifest["captures"].append(details)
        print(f"Saved {args.output / filename}", flush=True)

    def capture_mass_edit(page):
        """Open the real Cards action, preview a change, then cancel the popup."""
        captured = []
        errors = []

        def save_and_cancel(dialog):
            try:
                save_capture(dialog, "mass_edit.png", page.selected.name)
                captured.append(True)
            except Exception as error:
                errors.append(error)
            finally:
                dialog.reject()

        def prepare_popup():
            dialog = app.activeModalWidget()
            if not isinstance(dialog, CardMassEditDialog):
                errors.append(
                    RuntimeError("Mass Edit did not open the expected popup.")
                )
                if isinstance(dialog, QtWidgets.QDialog):
                    dialog.reject()
                return
            try:
                dialog.scope_input.setCurrentIndex(
                    dialog.scope_input.findData("Search results")
                )
                dialog.regex_input.setText(re.escape(page.selected.name))
                dialog.replacement_input.setText(page.selected.name + " (example)")
                dialog.descriptions_checkbox.setChecked(False)
                dialog._preview_replacement()
                if not dialog.changes:
                    raise RuntimeError("Mass Edit example produced no preview changes.")
                # Let the diff highlighter and popup layouts finish before grabbing.
                QtCore.QTimer.singleShot(200, lambda: save_and_cancel(dialog))
            except Exception as error:
                errors.append(error)
                dialog.reject()

        QtCore.QTimer.singleShot(100, prepare_popup)
        page.massEditButton.click()
        if errors:
            raise RuntimeError("Mass Edit capture failed.") from errors[0]
        if not captured:
            raise RuntimeError("Mass Edit popup was not captured.")
        settle(page)

    try:
        print("Loading the main window and asset thumbnails...", flush=True)
        window = MainWindow(splash)
        window.setWindowTitle("Floowandereeze & Modding")
        if args.windowed or args.offscreen:
            window.showNormal()
            window.resize(args.width, args.height)
            window.show()
        else:
            window.showMaximized()
        settle(window.mainStack.widget(11))
        for name in args.pages:
            index = PAGES.index(name)
            page = window.mainStack.widget(index)
            expected = {
                "config": "Config",
                "card_icon": "CardIcon",
                "deck_box": "DeckBox",
                "summon-animation": "SummonAnimation",
            }.get(name, name.title())
            if type(page).__name__ != expected:
                raise RuntimeError(
                    f"The {name} page failed to load; refusing to save a placeholder."
                )
            window._navigation_buttons[index].trigger()
            settle(page)
            for splitter in page.findChildren(QtWidgets.QSplitter):
                if splitter.orientation() == QtCore.Qt.Orientation.Vertical:
                    view = page.findChild(QtWidgets.QListView)
                    overhead = page.resultsPanel.height() - view.viewport().height()
                    results_height = max(
                        splitter.height() // 2,
                        2 * page.RESULT_ITEM_SIZE.height() + overhead + 12,
                    )
                    splitter.setSizes(
                        [
                            max(230, splitter.height() - results_height),
                            results_height,
                        ]
                    )
            if hasattr(page, "_queue_layout_update"):
                page._queue_layout_update()
            settle(page)
            selected = None
            if name == "config":
                # Block callbacks while redacting visible fields only.
                for field, text in (
                    (page.gameLine, r"C:\Games\Master Duel\LocalData\01234567"),
                    (page.bgLine, ""),
                ):
                    with QtCore.QSignalBlocker(field):
                        field.setText(text)
            elif name == "backups":
                page.service = BackupService(ROOT / "backups")
                page.refresh()  # Inventory only; never export, import, delete or restore.
            elif name == "summon-animation":
                page.search.setText(args.summon_search)
                settle(page)
                if page.model.rowCount() == 0:
                    raise RuntimeError("No summon matches --summon-search.")
                page.cardsView.setCurrentIndex(page.model.index(0, 0))
                settle(page)
                selected = page.cardTitle.text()
                if args.summon_source:
                    page.editor.use_source(str(args.summon_source))
                    settle(page)
                    if page.editor.plan is None:
                        raise RuntimeError("Summon preview preparation failed.")
                    page.editor.pause()
                    page.editor.slider.setValue(page.editor.slider.maximum() // 2)
                    # Display a neutral filename without invalidating the prepared preview.
                    with QtCore.QSignalBlocker(page.editor.source):
                        page.editor.source.setText(
                            "examples/" + args.summon_source.name
                        )
            elif name != "background":
                view_name, handler = {
                    "sleeve": ("sleevesView", "_on_sleeve_clicked"),
                    "card": ("cardsView", "_on_card_clicked"),
                    "card_icon": ("iconsList", "_on_icon_clicked"),
                    "face": ("facesView", "_on_face_clicked"),
                    "icon": ("iconsView", "_on_icon_clicked"),
                    "field": ("fieldsView", "_on_field_clicked"),
                    "wallpaper": ("wallpaperView", "_on_wallpaper_clicked"),
                    "coin": ("coinsView", "_on_coin_clicked"),
                    "deck_box": ("deck_boxesView", "_on_deck_box_clicked"),
                }[name]
                if name == "card":
                    page.searchEdit.setText(args.card_search)
                    page.searchButton.click()
                    settle(page)
                assets = page.model.fields if name == "field" else page.model.assets
                if not assets:
                    raise RuntimeError(f"No real assets available for {name}.")
                # Stable names and IDs make repeated runs choose the same item.
                candidates = sorted(
                    enumerate(assets),
                    key=lambda pair: (
                        not bool(getattr(pair[1], "display_name", None)),
                        getattr(pair[1], "display_name", None)
                        or getattr(pair[1], "name", ""),
                        pair[1].id,
                    ),
                )
                if name == "card_icon":
                    # Legacy sprite metadata can contain fractional crop dimensions;
                    # the current source-image handler requires integer dimensions.
                    candidates = [
                        (row, asset)
                        for row, asset in candidates
                        if isinstance(asset.width, int)
                        and isinstance(asset.height, int)
                    ]
                if not candidates:
                    raise RuntimeError(f"No compatible preview asset for {name}.")
                preferred = {
                    "sleeve": "Blue-Eyes White Dragon",
                    "card_icon": "DARK",
                }.get(name)
                matches = [
                    (row, asset)
                    for row, asset in candidates
                    if getattr(asset, "display_name", None) == preferred
                ]
                if preferred and matches:
                    candidates = matches
                row, asset = candidates[0]
                view = getattr(page, view_name)
                model_index = page.model.index(row, 0)
                view.setCurrentIndex(model_index)
                view.scrollTo(model_index)
                getattr(page, handler)(model_index)
                selected = (
                    getattr(asset, "display_name", None)
                    or getattr(asset, "name", None)
                    or str(asset.id)
                )
                settle(page)
            if name not in ("config", "backups", "summon-animation"):
                label = getattr(page, "current", None)
                pixmap = label.pixmap() if label is not None else page.preview.pixmap
                if pixmap is None or pixmap.isNull():
                    raise RuntimeError(f"No installed texture loaded for {name}.")
                example = Path("examples") / f"{name}.png"
                example.parent.mkdir(exist_ok=True)
                if not pixmap.save(str(example)):
                    raise RuntimeError(f"Cannot save preview source for {name}.")
                page._set_image(str(example))
                if name == "card_icon":
                    # The centered fit-control wrapper needs its size hint refreshed
                    # after the icon label receives its final fixed dimensions.
                    page.preview.parentWidget().adjustSize()
            settle(page)
            page.setFocus()
            filename = name.replace("-", "_") + ".png"
            if name == "summon-animation":
                filename = (
                    "summon-frames.png"
                    if args.summon_source
                    else "summon-animation.png"
                )
            save_capture(window, filename, selected)
            if name == "card":
                capture_mass_edit(page)
            if name == "summon-animation" and not args.summon_source:
                model = CardOcgModel if APP_CONFIG.asset_region == "ocg" else CardModel
                card = session.query(model).filter(model.name == selected).first()
                if card is None:
                    raise RuntimeError("No matching card artwork; use --summon-source.")
                icon = fetch_bundle_thumb(card.bundle, None)
                if icon is None:
                    icon = fetch_bundle_thumb(card.bundle, None, True)
                if icon is None or icon.isNull():
                    raise RuntimeError("No installed summon example artwork.")
                example = Path("examples/summon-frames")
                example.mkdir(parents=True)
                artwork = example / "frame001.png"
                if not icon.pixmap(icon.availableSizes()[0]).save(str(artwork)):
                    raise RuntimeError("Could not save summon example artwork.")
                page.editor.use_source(str(example))
                settle(page)
                if page.editor.plan is None:
                    raise RuntimeError("Default summon preview preparation failed.")
                page.editor.pause()
                page.editor.slider.setValue(page.editor.slider.maximum() // 2)
                settle(page)
                save_capture(window, "summon-frames.png", selected)
                if args.memory_warning:
                    from PIL import Image

                    large = Path("examples/large-frames")
                    large.mkdir()
                    with Image.open(artwork) as image:
                        image.resize((6000, 6000)).save(large / "frame001.png")
                    warning_expected = True
                    page.editor.use_source(str(large))
                    settle(page)
                    warning_expected = False
                    if not warning_captured:
                        raise RuntimeError(
                            "The expected large-import warning did not appear."
                        )
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Saved capture manifest: {args.manifest}", flush=True)
    finally:
        # Do not destroy a QThread while it is still using its page or database.
        if window is not None:
            for page in window.findChildren(QtWidgets.QWidget):
                if hasattr(page, "is_busy"):
                    settle(page)
            window.close()
            window.deleteLater()
            app.processEvents()
        guard.stop()
        session.rollback()
        session.close()
        engine.dispose()


def main():
    """Resolve user paths before entering the disposable working directory."""
    args = arguments()
    args.database = args.database.resolve(strict=True)
    args.output = args.output.resolve()
    args.manifest = (
        ROOT / "build/docs-captures/manifest.json"
        if args.output == (ROOT / "docs/assets/ui").resolve()
        else args.output / "manifest.json"
    )
    if args.width < 1280 or args.height < 900:
        raise ValueError("Use at least 1280 x 900 to keep editor controls visible.")
    if args.summon_source:
        args.summon_source = args.summon_source.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=True)
    print(f"Screenshot destination: {args.output}", flush=True)
    previous = Path.cwd()
    try:
        (ROOT / "build").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="floo-docs-", dir=ROOT / "build"
        ) as directory:
            try:
                capture(args, Path(directory))
            finally:
                os.chdir(previous)
    finally:
        os.chdir(previous)


if __name__ == "__main__":
    main()
