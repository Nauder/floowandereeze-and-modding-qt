.\build_qt.ps1

pyinstaller `
    --onefile `
    --noconsole `
    --icon "./qtdesigner/images/icon.ico" `
    --add-data ".venv\Lib\site-packages\UnityPy;UnityPy/" `
    --add-data "pages/ui;pages/ui/" `
    --hidden-import "fastparquet" `
    --name "Floowandereeze & Modding" `
    .\main.py