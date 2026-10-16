# Recreate documentation screenshots

`tools/capture_docs.py` opens the real PySide6 main window, loads assets from the development database and installed game, selects an asset in each editor, and saves PNG captures. It uses the app's widgets, theme, toolbar, search and image preparation code. No mock widgets or invented asset records are used.

## Prepare and capture

1. Install the runtime dependencies in `.venv` and configure the app's **Game Path**. Use **Check** in Configuration to populate the development database. Download the assets you want to show through Master Duel, then close the game.
2. From the repository root, rebuild the generated Qt modules and capture:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   .\build_qt.ps1
   python tools/capture_docs.py --memory-warning
   ```

3. Inspect the updated PNGs in `docs/assets/ui/`. The helper recreates missing images and replaces existing screenshots there by default. Each saved image's absolute path is printed in the terminal. `build/docs-captures/manifest.json` records the Qt version, capture dimensions and selected asset names.

To regenerate just the Deck Box screenshot used by the documentation:

```powershell
python tools/capture_docs.py --pages deck_box
```

Older versions saved only to `build/docs-captures/`; those images did not update the documentation until copied into `docs/assets/ui/`.

The helper maximizes the window to the desktop by default, matching normal app startup. Qt saves the screen's native pixel density; the manifest records each PNG's actual and logical sizes and the window mode. The responsive editor splitters reserve space for at least two complete selector rows, and the helper verifies the visible rows before accepting each capture. The window appears briefly and switches tabs automatically; let the run finish without interacting with it. Initial thumbnail loading can take some time. Captures include the application contents and toolbar, without the operating system's title bar or desktop.

Capture only selected pages, use another database, or choose a different card search:

```powershell
python tools/capture_docs.py --pages deck_box coin card --card-search "Blue-Eyes"
python tools/capture_docs.py --database local/development.db --output build/review-captures
```

`--pages` accepts `config`, `sleeve`, `card`, `card_icon`, `face`, `background`, `icon`, `field`, `wallpaper`, `coin`, `deck_box`, `summon-animation` and `backups`. For a fixed window size, use `--windowed --width 1600 --height 1000` (minimum 1280 × 900). `--offscreen` also uses the fixed window size and renders without displaying a window; platform styles can differ, so use the default maximized Windows capture for published screenshots.

## Data and privacy

The helper opens the source SQLite database read-only and uses SQLite's backup API to make a consistent temporary copy under `build/`. App migrations, configuration callbacks and favorite state changes affect only that copy. Qt settings and image-processing temporary files are isolated too. The helper never presses Replace, Restore, Check, Import or Remove, and never writes game bundles. Backups uses the real repository backup inventory for display only.

Configuration shows a generic example game path, clears the custom background path, and uses the shipped application background. These are display substitutions; the real installation path is still used internally to read textures. Review every image before publication, especially asset names, metadata repository/branch settings, and backup filenames, which reflect your local data.

For static editors the helper saves the selected installed artwork to a temporary `examples/` image and loads it through the normal source-image handler. Current and Preview therefore deliberately show the same artwork. This demonstrates the actual prepared UI without applying a mod. Card Icons selects an entry with integer texture dimensions because the current preview handler cannot resize fractional dimensions in legacy sprite metadata. Database contents, installed mods, missing bundles and platform fonts can change the output. A failed page, unexpected modal error or missing preview stops the run instead of publishing a placeholder; earlier PNGs can remain in the review folder.

## Mass Edit popup

Capturing `card` also saves `mass_edit.png`. The helper clicks the Cards page's **Mass Edit** action, chooses **Search results**, and previews adding ` (example)` to the selected card's name. The popup shows real scope counts, before/after text and highlighted differences from the development data. It then cancels the dialog without applying the changes. The popup retains its normal dialog size while the main app stays maximized.

```powershell
python tools/capture_docs.py --pages card
```

## Summon previews

The default summon capture saves both `summon-animation.png` with a real card selected and `summon-frames.png` with its installed card artwork imported as a one-frame PNG sequence. The latter is a real prepared preview against the installed animation bundles; it does not demonstrate moving source artwork. Selecting a different summon requires matching card artwork in the regional card metadata. You can instead supply your own GIF, MP4 or PNG frames folder:

```powershell
python tools/capture_docs.py --pages summon-animation --summon-search "Blue-Eyes White Dragon" --summon-source local/example.gif
```

With a supplied source, this saves only `summon-frames.png`, pauses playback near the middle, and shows a neutral source filename. Preparation runs through the app's normal worker and validation; no replacement is applied. Use an input small enough to avoid the large-import confirmation: the helper cancels unexpected dialogs and fails the capture.

`--memory-warning` adds `summon-memory-warning.png` when using the default extracted artwork. It creates a real 6000 × 6000 PNG example in the temporary folder, starts the normal import, captures the resulting **Large animation import** dialog, and cancels it. The warning comes from the actual input dimensions and memory estimate; metadata and the warning text are not mocked. Enlarging the example briefly uses additional memory, but the expensive conversion is never approved.

## Publish reviewed captures

The configuration guides share `config.png`, and the shared editor layout guide reuses `deck_box.png`. All generated PNG filenames match the current documentation image references. The default command updates them directly. To review a separate capture set first, use `--output`; its manifest is saved beside its PNGs. Then copy the reviewed images into the documentation:

```powershell
python tools/capture_docs.py --memory-warning --output build/review-captures
# Inspect build/review-captures/*.png before copying.
Copy-Item build/review-captures/*.png docs/assets/ui/
```

After copying the reviewed images, update any captions that describe synthetic data and validate the documentation:

```powershell
python -m mkdocs build --strict --site-dir build/docs-preview
```
