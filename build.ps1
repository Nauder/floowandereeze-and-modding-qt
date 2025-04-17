.\build_qt.ps1

pyinstaller `
    --onefile `
    --noconsole `
    --icon "./qtdesigner/images/icon.ico" `
    --add-data "C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\site-packages\UnityPy;UnityPy/" `
    --hidden-import "fastparquet" `
    --name "Floowandereeze & Modding" `
    .\main.py