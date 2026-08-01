.\build_qt.ps1

& .\.venv\Scripts\python.exe -m PyInstaller `
    --clean `
    --onefile `
    --noconsole `
    --icon "./qtdesigner/images/icon.ico" `
    --add-data ".venv\Lib\site-packages\UnityPy;UnityPy/" `
    --collect-binaries "fmod_toolkit" `
    --collect-data "archspec" `
    --hidden-import "fastparquet" `
    --hidden-import "numpy._core._exceptions" `
    --name "Floowandereeze & Modding" `
    .\main.py
