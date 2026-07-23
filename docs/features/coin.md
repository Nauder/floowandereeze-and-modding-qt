# Coin Editor

The Coin Editor replaces duel coin textures and keeps the game's small, medium, and large versions together.

> **Screenshot placeholder — Coin Editor:** Capture the Coins page with a selected coin, Current and Preview images, Favorite enabled, the Favorites filter, and several items in the Results grid.

## Replace a coin

1. Select a coin from **Results**.
2. Choose a square PNG or JPEG with **Select**, or drag it onto the page.
3. Check **Preview** and choose **Replace**.

The app creates the required small, medium, and large square textures from the same source image. Use a square source to prevent distortion; PNG is recommended for transparency.

## Other actions

- **Favorite** marks the selected coin; **Favorites** filters the result grid.
- **Extract** saves all three size textures under `images\coins`.
- **Copy** saves all three Unity bundles under `bundles\coins`.
- **Restore** uses the backup of the largest version to rebuild all three sizes.

Enable backups before the first replacement. Only the largest original texture is stored as the automatic backup.
