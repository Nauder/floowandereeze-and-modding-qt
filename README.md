# Floowandereeze & Modding

A powerful modding tool for Yu-Gi-Oh! Master Duel, built with PySide6 (Qt6) for Windows (Under Development).

[![Pylint](https://github.com/Nauder/floowandereeze-and-modding-qt/actions/workflows/pylint.yml/badge.svg)](https://github.com/Nauder/floowandereeze-and-modding-qt/actions/workflows/pylint.yml)
[![Black](https://github.com/Nauder/floowandereeze-and-modding-qt/actions/workflows/black.yml/badge.svg)](https://github.com/Nauder/floowandereeze-and-modding-qt/actions/workflows/black.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg?logo=python&logoColor=white)](https://www.python.org)
[![PySide6](https://img.shields.io/badge/PySide6-6.7.2-41CD52.svg?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.34-29B6F6.svg?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![UnityPy](https://img.shields.io/badge/UnityPy-1.10.18-000000.svg?logo=unity&logoColor=white)](https://github.com/K0lb3/UnityPy)
[![Windows](https://img.shields.io/badge/Windows-10+-0078D6.svg?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Development](#development)
- [Building](#building)
- [License](#license)
- [Contributing](#contributing)
- [Credits](#credits)

## Features

- Modern, dark-themed user interface
- Unity asset extraction and manipulation
- Database management for asset data
- Bundle file handling
- Texture and audio file processing
- Card data visualization and editing

## Requirements

- Windows 10 or later
- Python 3.8 or later
- Yu-Gi-Oh! Master Duel installed with the in-game download

## Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/Nauder/floowandereeze-and-modding-qt.git
    cd floowandereeze-and-modding-qt
    ```

2. Create and activate a virtual environment:

    ```bash
    python -m venv .venv
    .venv\Scripts\activate
    ```

3. Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

Run the development environment:

```powershell
.\dev.ps1
```

This script will:

- Activate the virtual environment
- Compile Qt UI files and resources using `build_qt.ps1`
- Launch the application

Note: The `build_qt.ps1` script is used to:

- Compile Qt resource files (`.qrc`) into Python modules
- Convert Qt Designer UI files (`.ui`) into Python code
- These steps are necessary for the application to run properly

## Project Structure

```txt
floo-qt/
├── pages/            # Main application pages and windows
│   └── models/       # Asset List Models for data pages
├── widgets/          # Custom Qt widgets
├── services/         # Core functionality services
├── util/             # Utility functions and helpers
├── database/         # Database models and operations
├── unity/            # Unity asset handling
├── dialogs/          # Custom dialog windows
├── qtdesigner/       # Qt Designer UI files
│   ├── ui/           # UI files (.ui)
│   └── images/       # Application images and resources
├── main.py           # Application entry point
├── requirements.txt  # Python dependencies
├── build.ps1         # Build script for executable
├── build_qt.ps1      # Qt UI compilation script
└── dev.ps1           # Development environment script
```

## Development

- The project uses PySide6 for the GUI, with Pyside Designer ui files
- SQLAlchemy for database operations
- UnityPy for Unity asset handling
- Various other utilities for file processing and data manipulation
- Currently, development is focused on Windows, as that is the main supported desktop OS for Master Duel

## Building

To create a standalone executable:

```powershell
.\build.ps1
```

This script will:

1. Compile Qt UI files and resources using `build_qt.ps1`
2. Create a single-file executable using PyInstaller
3. Include necessary dependencies and UnityPy assets
4. Generate the executable in the `dist` directory

## License

This project is licensed under the terms specified in the LICENSE file.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Credits

- [Akintos](https://gist.github.com/akintos/04e2494c62184d2d4384078b0511673b)
and [Timelic](https://github.com/timelic/master-duel-chinese-translation-switch) for the decoding and encoding scripts.
