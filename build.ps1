.\build_qt.ps1

& python -m PyInstaller `
    --clean `
    --onefile `
    --noconsole `
    --icon "./qtdesigner/images/icon.ico" `
    --collect-all "UnityPy" `
    --collect-binaries "fmod_toolkit" `
    --collect-data "archspec" `
    --hidden-import "fastparquet" `
    --hidden-import "numpy._core._exceptions" `
    --name "Floowandereeze & Modding" `
    .\main.py
