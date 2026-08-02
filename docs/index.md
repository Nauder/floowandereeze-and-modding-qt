# Floowandereeze & Modding

Floowandereeze & Modding is a Windows desktop tool for replacing visual assets and editing card text in Yu-Gi-Oh! Master Duel.

It currently supports:

- Card artwork, names, and descriptions
- Card icons from the game's shared sprite atlas
- Card faces and sleeves
- Player icons and coins
- Duel fields
- Home backgrounds and wallpapers

The app edits files in your Master Duel installation. Game updates can replace those files, and two mods that change the same bundle can overwrite one another. Read [Backups and safe modding](using-the-editors.md#backups-and-safe-modding) before making your first replacement.

![application overview](./assets/ui/card.png)

## Start here

1. Follow [Getting started](getting-started.md) to install the app, select the correct player-data folder, and download the asset index.
2. Read [Using the editors](using-the-editors.md) for the controls shared by most pages.
3. Open the guide for the asset you want to change.

## Editor guides

| Editor | What it changes | Notable tools |
| --- | --- | --- |
| [Cards](features/card.md) | Card artwork, names, and descriptions | Search, favorites, individual and mass text editing |
| [Card Icons](features/card-icon.md) | Small card-related graphics in the shared atlas | Atlas-region extraction, replacement, and restore |
| [Card Faces](features/face.md) | Card frame/face textures | Replace, extract, and restore |
| [Sleeves](features/sleeve.md) | Card sleeve textures | Optional solid or fade-in border, favorites |
| [Player Icons](features/icon.md) | Player profile icons | Replaces all three resolutions, favorites |
| [Coins](features/coin.md) | Duel coin textures | Replaces all three resolutions, favorites |
| [Duel Fields](features/field.md) | Supported duel field surface textures | Extract and copy bundle |
| [Background](features/background.md) | The shared home/duel background texture | Fixed 1920×1080 replacement |
| [Wallpapers](features/wallpaper.md) | Home wallpaper foreground/background pair | Extract and copy both bundles |
| [Configuration](features/config.md) | Paths, data, backups, appearance, and bundle settings | Steam auto-detection and bulk maintenance |

If something does not work as expected, see [Troubleshooting](troubleshooting.md).

## Important limitations

- The application is Windows-focused and expects the Steam installation layout.
- Close Master Duel before replacing or restoring assets.
- Master Duel updates may restore original game files. Use **Reapply All** for saved card-text edits; image mods usually need to be replaced again.
- Field layouts are not standardized, so some fields are unsupported or may replace the wrong portion.
- Wallpapers may contain extra layers and effects that this app does not change.
