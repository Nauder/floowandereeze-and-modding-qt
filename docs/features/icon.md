# Icon Editor

The Icon Editor page allows you to modify player icons in Yu-Gi-Oh! Master Duel. This page provides functionality to
view, replace, and manage icon assets.

![Icon Page Preview](../assets/ui/icon.png)

## Features

- Icon list with preview
- Icon texture replacement
- Texture extraction for all sizes
- Bundle copying
- Backup and restore functionality
- Real-time preview updates

## Interface Elements

### Icon List

- Displays all available player icons
- Click on an icon to select it for editing
- Shows the icon bundle information

### Preview Section

- Shows the currently selected icon
- Displays the medium-sized version (256x256)
- Updates in real-time when changes are made

### Action Buttons

- **Select Image**: Choose a new icon image
- **Replace**: Apply the selected image to the icon
- **Copy**: Copy the icon bundle to the icons folder
- **Extract**: Extract all icon textures
- **Restore**: Restore the icon from backup

### Information Display

- Shows the icon name
- Displays bundle names for all three sizes:
  - Small (S)
  - Medium (M)
  - Big (B)

## Usage

1. **Selecting an Icon**
      - Click on an icon in the list to select it
      - The preview will update to show the selected icon
      - Action buttons will become enabled
      - Bundle information for all sizes will be displayed

2. **Replacing Icon**
      - Click "Select Image" to choose a new icon
      - Preview the selected image
      - Click "Replace" to apply the changes
      - A backup will be created if enabled in settings

3. **Extracting Textures**
      - Select an icon
      - Click "Extract" to save all textures
      - The textures will be saved to the "icons" folder

4. **Managing Backups**
      - Select a modified icon
      - Click "Restore" to revert to the original version
      - A notification will indicate if backup exists

## Notes

- All icon sizes are extracted when using the extract function
- The preview shows the medium-sized version (256x256)
- The application creates backups automatically if enabled in settings
- Backups are created using the big-sized version of the icon
