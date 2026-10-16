# Summon compatibility audit

This developer command checks every summon card available in the configured metadata against the real replacement pipeline. It uses the same Global/OCG installation, game path and preferred regional assets as the Summons tab.

From the repository root, run:

```powershell
.\.venv\Scripts\python.exe tools/audit_summon_animations.py
```

Reports are saved to `build/summon-audit/report.json` and `report.csv`. JSON includes per-card, per-quality, per-format results and the failure stage. CSV provides a flat list for filtering. If a spreadsheet locks the CSV file, JSON progress continues; close the CSV to allow its next refresh.

Progress logs use UTF-8 so card names such as `Evil★Twin` can be printed safely on Windows. Watch a redirected log with `Get-Content -Encoding UTF8 -Tail 10 -Wait path/to/audit.log`.

The full audit can take hours for a large collection: texture compression runs for every supported card. Results update after each card. Each card runs in an isolated process, with two processes by default, and a 180-second timeout. A timeout or native crash is recorded as a failure and the remaining cards continue.

## What is checked

- Every card with skeleton metadata, including alternate artworks.
- Every available high/lower quality target, using synthetic GIF and PNG inputs.
- Actual timeline references, dependencies, profiles, materials and supported prefab components.
- Framing, atlas capacity and frame generation at the GUI defaults: 256-pixel long edge and 30 output FPS.
- Texture encoding, compressed format/mipmap preservation, bundle save/reload, and unchanged objects/resources.

The synthetic input has two different frames, transparent padding and opaque artwork. When GIF and PNG produce exactly the same pixels, timing, target metadata and dependency checksums, native serialization is performed once for that quality; the other format records which result it reuses.

The service discards generated bundle bytes after validation. It creates no game backups, changes no game files and does not update the application's database. Reports must be outside the game asset and backup directories and must not overwrite the database. Only reports and temporary synthetic input are written.

## Options

```powershell
# Faster generation/validation scan; skips texture encoding and save/reload
.\.venv\Scripts\python.exe tools/audit_summon_animations.py --preview-only --report build/summon-audit/preview.json

# Check selected cards
.\.venv\Scripts\python.exe tools/audit_summon_animations.py --card 20567 --card 20569

# Resume an interrupted run with unchanged metadata, settings, importer code and dependency bytes
.\.venv\Scripts\python.exe tools/audit_summon_animations.py --resume

# Try smaller frames when investigating atlas capacity failures
.\.venv\Scripts\python.exe tools/audit_summon_animations.py --edge 32 --report build/summon-audit/small-frames.json
```

Use `--jobs 1` through `--jobs 4` to control parallelism, `--timeout` to change the per-card limit, and `--database` to use another local database snapshot. To rerun previously failed cards after changing the importer, start a fresh report rather than resuming results from the previous implementation. Resume reuses only passed cards whose dependency checksums still match; failures and missing assets are retried.

## Fixing failures in batches

Use the JSON/CSV failure list to group cards by their error, then rerun just that group with a separate report after a fix:

```powershell
.\.venv\Scripts\python.exe tools/audit_summon_animations.py --card 12590 --card 16386 --report build/summon-audit/batch-1.json
```

Keep the batch report separate from the catalog scan so progress is not overwritten. Each worker records the importer revision it tested. A scan freezes its importer modules in a temporary snapshot, so edits made for another batch do not invalidate workers that are already queued. Resume still requires unchanged importer code; start a new report after fixes to test the new revision. Rerun affected cards against the final revision before claiming catalog compatibility.

## Reading results

| Status | Meaning |
| --- | --- |
| `passed` | Every available quality and input format passed the selected audit mode. |
| `failed` | At least one compatibility, generation, encoding, verification or worker check failed. Read its `stage` and `error`. |
| `missing_assets` | Required mapped bundles are not downloaded; compatibility could not be checked. |

A graph failure applies to both formats and all quality modes because they share the same playback validation. Other failures remain specific to their input format and quality. Cards without skeleton metadata do not appear in the audit because they are not selectable summon replacements.

An incomplete JSON report has `complete: false`. Do not treat its current counts as the final catalog result. Exit code 0 means the entire selected catalog passed; code 1 means there were failures or missing assets.

Passing checks means this synthetic input completed the requested pipeline. It does not guarantee that arbitrary GIFs/PNG sequences fit the atlas, or that the replacement looks correct in-game. Use the [GIF/PNG guide](summon-frames.md) for limits and verify playback, placement and shaders in the game.

Synthetic regression coverage runs without installed game assets:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_summon_audit.py
```
