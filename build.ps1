.\build_qt.ps1

pyinstaller `
    --onefile `
    --noconsole `
    --icon "./qtdesigner/images/icon.ico" `
    --add-data "$env:LOCALAPPDATA\Programs\Python\Python311\Lib\site-packages\UnityPy;UnityPy/" `
    --hidden-import "fastparquet" `
    --name "Floowandereeze & Modding" `
    .\main.py