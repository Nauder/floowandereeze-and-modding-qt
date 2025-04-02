# Main Window

The main window serves as the central hub of the Floowandereeze & Modding application. It provides navigation between different editing pages and manages the overall application state.

## Features

- Navigation toolbar for switching between different editing pages
- Dynamic page loading based on game path validation
- Customizable background image support
- Splash screen integration for loading progress
- Error handling for invalid game paths

## Navigation

The main window provides a toolbar with buttons to navigate between different pages:

- Configuration
- Card Sleeve Editor
- Card Editor
- Card Face Editor
- Background Editor
- Icon Editor
- Duel Field Editor
- Wallpaper Editor

## Game Path Validation

The application validates the game path on startup:

- If the game path is valid, all editing pages are loaded
- If the game path is invalid or not set:
  - Only the Configuration page is loaded
  - The navigation toolbar is disabled
  - A warning toast notification is displayed

## Background Customization

The main window supports custom background images:

- Background can be set through the configuration
- Falls back to default background if custom background is not set or invalid
- Background image is applied using CSS border-image property

## Usage

1. Launch the application
2. If the game path is not set or invalid:
   - Use the Configuration page to set the correct game path
   - Restart the application after setting the path
3. Once the game path is valid:
   - Use the toolbar to navigate between different editing pages
   - Each page provides specific functionality for modifying game assets
