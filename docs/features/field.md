# Duel Field Editor

The Duel Field Editor page allows you to modify duel field textures in Yu-Gi-Oh! Master Duel. This page provides
functionality to view, replace, and manage duel field assets.

![Field Page Preview](../assets/ui/field.png)

## Features

- Duel field list with preview
- Field texture replacement
- Texture extraction
- Bundle copying
- Real-time preview updates

## Interface Elements

### Duel Field List

- Displays all available duel fields
- Click on a field to select it for editing
- Shows the field bundle information

### Preview Section

- Shows the currently selected duel field
- Displays the field's bundle information
- Updates in real-time when changes are made

### Action Buttons

- **Select Image**: Choose a new field texture image
- **Replace**: Apply the selected image to the field
- **Copy**: Copy the field bundle to the fields folder
- **Extract**: Extract the field texture

## Usage

1. **Selecting a Duel Field**
      - Click on a field in the list to select it
      - The preview will update to show the selected field
      - Action buttons will become enabled

2. **Replacing Field Texture**
      - Click "Select Image" to choose a new field texture
      - Preview the selected image
      - Click "Replace" to apply the changes

3. **Extracting Textures**
      - Select a field
      - Click "Extract" to save the texture
      - The texture will be saved to the "fields" folder

4. **Copying Fields**
      - Select a field
      - Click "Copy" to save the bundle
      - The field will be copied to the "fields" folder

## Notes

- If a field is missing from the list, it has a texture that does not follow any standard supported by the app, so it cannot be replaced through it.
- Field replacement is inherently buggy, as they are not standarized like other assets. The app has educated guesses as to what part of the field to replace, but the wrong parts may be affected.
