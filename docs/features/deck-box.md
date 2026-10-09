# Deck Box Editor

The Deck Box Editor replaces deck box artwork and handles its different resolutions automatically.

![Deck Box Editor](../assets/ui/deck_box.png)

## Replace a deck box

1. Open **Deck Boxes** and select a box from **Results**.
2. Choose its **Texture variant**: **Normal**, **Left Facing**, or **Open**.
3. Use **Select** or drop a PNG or JPEG onto the page.
4. Choose **Stretch** or **Crop** and check **Preview**.
5. Choose **Replace**, then check the result in Master Duel.

Current and Preview use the large version of the selected orientation. Replace applies the same artwork to all matching resolutions automatically, preserving each texture's dimensions. Normal includes small, medium, and large; Left Facing and Open each include medium and large. Other orientations remain unchanged. PNG supports transparency.

## Other actions

- **Favorite** marks the deck box; **Favorites** filters Results.
- **Extract** saves the large texture of the selected orientation under `images\deck_boxes`.
- **Copy** saves all Unity bundles for the selected orientation under `bundles\deck_boxes`.
- **Restore** restores all resolutions of the selected orientation from `backups\deck_boxes`.

Enable backups in [Configuration](config.md) before replacing textures. Each resolution gets its own backup before its first replacement; existing backups are preserved. Restore requires backups for all resolutions of the selected orientation, and restores each original texture separately. Older backups made for only one resolution can still be restored individually through Configuration's bulk restore. Configuration's bulk restore and clear actions also include deck box backups.

The editor changes the first Texture2D in each bundle. It does not change meshes, materials, or additional textures. Missing game bundles must be downloaded by the game before editing; use Configuration's **Check** to refresh an outdated asset index.
