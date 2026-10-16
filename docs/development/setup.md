# Run from source

Developers can use the repository's PowerShell workflow:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\dev.ps1
```

`dev.ps1` activates `.venv`, regenerates the Qt UI/resources, and launches `main.py`. The project currently targets Python 3.11 for development.
