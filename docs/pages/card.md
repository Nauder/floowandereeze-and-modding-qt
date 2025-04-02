# Card Editor

The Card Editor page allows you to modify card art and information in Yu-Gi-Oh! Master Duel. This page provides functionality to view, edit, replace, and manage card assets.

## Features

- Card list with search functionality
- Card preview and editing
- Card art replacement
- Card name and description editing
- Card texture extraction
- Backup and restore functionality
- Auto-complete search suggestions

## Interface Elements

### Card List

- Displays all available cards in a thumbnail view
- Click on a card to select it for editing
- Shows card names bellow thumbnails

### Preview Section

- Shows the currently selected card's art
- Displays the card's bundle information
- Updates in real-time when changes are made

### Action Buttons

- **Select Image**: Choose a new card art image
- **Replace**: Apply the selected image to the card
- **Copy**: Copy the card bundle to the cards folder
- **Extract**: Extract the card's texture
- **Restore**: Restore the card from backup
- **Edit**: Open the card text editor dialog

### Search

- Search box with auto-complete suggestions
- Minimum 3 characters required for search
- Case-insensitive search
- Matches partial text within original (not modded) card names

## Usage

1. **Searching Cards**
   - Type at least 3 characters in the search box
   - Use auto-complete suggestions for quick selection
   - The list will filter to show matching cards after clicking the search button or pressing ENTER

2. **Selecting a Card**
   - Click on a card in the list to select it
   - The preview will update to show the selected card
   - Action buttons will become enabled

3. **Replacing Card Art**
   - Click "Select Image" to choose a new card art
   - Preview the selected image
   - Click "Replace" to apply the changes
   - A backup will be created if enabled in settings

4. **Editing Card Text**
   - Select a card
   - Click "Edit" to open the text editor
   - Modify the card name and/or description
   - Click OK to save changes (can take a **long time**, depending on available resources)

5. **Managing Backups**
   - Select a modified card
   - Click "Restore" to revert to the original version
   - A notification will indicate if backup exists

## Notes

- The application creates backups automatically if enabled in settings
- Unity3D cards cannot be copied but can be extracted
- Card text changes can take a while to finish
- The search feature requires at least 3 characters to prevent performance issues
- Pendulum cards are currently displayed improperly, as the preview is square and their art is not, causing stretching. The functionalities themselves work properly
