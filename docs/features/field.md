# Duel Field Editor

The Duel Field Editor replaces the supported playable surface region of a duel field.

> **Screenshot placeholder — Duel Field Editor:** Capture the redesigned Fields page with Current and Preview panels, a selected field, editor actions, Results grid, and draggable splitter.

## Replace a field

1. Select a field from **Results**.
2. Choose a PNG or JPEG with **Select**, or drag it onto the page.
3. Check **Preview** and choose **Replace**.
4. Test the result in a duel from both player perspectives.

The app uses metadata to choose a top, bottom, or flipped placement and modifies the texture named like the supported near-field base color.

## Extract and copy

- **Extract** saves the supported field texture under `images\fields`.
- **Copy** saves the complete Unity bundle under `bundles\fields`.

This editor does not currently provide per-field backup or Restore controls. Make an extracted texture and bundle copy before replacing a field.

## Limitations

Master Duel fields are not standardized. Fields whose texture layout is not recognized are omitted from the list. For supported entries, the app uses known coordinates and orientation flags, but some fields may still replace the wrong region or appear flipped.
