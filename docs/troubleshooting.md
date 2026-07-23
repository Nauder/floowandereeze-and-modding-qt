# Troubleshooting

## Only Configuration is available

The saved game path is missing or invalid. Use **Auto-detect**, or manually select the player-ID folder under Master Duel's `LocalData` directory. Restart the app after saving a valid path.

If manual selection reports that the Unity3D file cannot be found, check that the path ends at the player ID and that the in-game data download has completed.

## Auto-detect finds no profiles

- Confirm that Master Duel was installed with Steam and launched at least once.
- Complete the game's data download.
- If Steam or the game is in an unusual location, use **Select** and browse to the player-ID folder manually.
- With multiple Steam accounts, verify that you chose the profile containing the assets you use in game.

## An editor is missing assets or fails to load

Open **Configuration** and choose **Check** to download the latest card and asset index. Restart the app afterward. Individual tabs display an error panel if their data could not be loaded; that message is useful when reporting a bug.

Some duel fields are intentionally omitted because their textures do not follow a layout the editor supports.

## Replace does nothing or is disabled

Select an asset in **Results** and select or drop a source image. Card Icons explicitly require both before **Replace** becomes available. Use a PNG or JPEG if a dragged file is not accepted.

Close Master Duel before trying again. The game or another process may be holding a bundle open.

## A replacement looks stretched, cropped, or transparent

- Start with an image matching the original texture's aspect ratio.
- Use PNG when alpha transparency is required.
- Extract the original texture to use its canvas dimensions as a template.
- For Wallpaper, read its [layer limitations](features/wallpaper.md#limitations).
- For Fields, the editor's selected region or orientation may not match that particular field.

## Restore says that no backup was found

The asset was changed before backups were enabled, the backup was cleared, or a backup was never created for that asset. The app cannot reconstruct the original from its database. Steam's file verification can restore game files, but it may remove all installed mods.

## A game update removed my mods

This is expected when the update replaces modified bundles. Refresh app data with **Check**, then replace the image assets again. Use **Reapply All** to write card-name and description edits saved in the app database back to the current game files.

## Card text editing fails or takes a long time

Card text is stored in shared metadata. The app refreshes and rewrites those files cautiously, so individual, regex, restore, and reapply operations can take noticeably longer than image replacement. Do not close the app during the operation.

If the app reports that a specific TextAsset cannot be found, run **Check** first. Do not keep retrying against out-of-date game data.

## Reporting a problem

Open an issue in the [GitHub repository](https://github.com/Nauder/floowandereeze-and-modding-qt/issues) and include:

- The application version or release filename
- Your Windows version
- The editor and action involved
- The exact notification or error-panel text
- Whether Master Duel had just updated
- A screenshot with player IDs and personal paths hidden
