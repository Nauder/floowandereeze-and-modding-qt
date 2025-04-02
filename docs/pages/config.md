# Configuration

The Configuration page allows you to manage application settings and perform maintenance tasks in Yu-Gi-Oh! Master Duel. This page provides functionality to configure game paths, update data, manage backups, and customize the application appearance.

## Features

- Game path configuration
- Data update management
- Backup system configuration
- Application appearance customization
- Asset compression settings
- Mipmap count configuration
- Bulk backup management

## Interface Elements

### Game Path Settings

- **Game Path**: Set the path to the Master Duel installation, up to the player ID folder
- **Update Button**: Check and update app data
- **Version Display**: Show current data version

### Backup Management

- **Enable Backups**: Toggle automatic backup creation
- **Restore All**: Restore all modified assets with backups to their original state
- **Clear Backups**: Delete all backup files

### Appearance Settings

- **Background Image**: Set custom application background
- **Reset Background**: Remove custom background

### Asset Settings

- **Mipmap Count**: Configure texture mipmap levels (Default 10)
- **Compression Options**:
  - None
  - LZMA
  - LZ4
  - LZ4HC
  - LZHAM

## Usage

1. **Setting Game Path**
   - Click "Select Game Folder" to choose Master Duel installation
   - Path is validated before being saved
   - Application restart required after setting path, so assets are updated

2. **Updating Data**
   - Set game path first
   - Click "Update" to check for new data
   - Updates are downloaded automatically if available

3. **Managing Backups**
   - Toggle "Enable Backups" to control automatic backup creation
   - Use "Restore All" to revert all changes
   - Use "Clear Backups" to remove backup files

4. **Customizing Appearance**
   - Click "Select Background" to choose custom background
   - Use "Reset Background" to remove custom background
   - Changes are applied immediately
   - The app has a dark theme, so bright backgrounds are not reccomended

5. **Configuring Asset Settings**
   - Set desired mipmap count (default: 10)
   - Choose compression method for new assets
   - Settings affect all new asset replacements

## Notes

- Game path must be set before using most features
- Data updates require a valid game path first
- Backup system affects all asset types
- Asset settings affect all new replacements
- Some changes require application restart
- Backups create local copies of assets, so they take storage space
