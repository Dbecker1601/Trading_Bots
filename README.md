# Trading_Bots

## Databento API Key sicher hinterlegen

1. Kopiere die Vorlage:
   cp .env.example .env

2. Trage deinen echten Key in `.env` ein:
   DATABENTO_API_KEY=dein_echter_databento_key

Wichtig:
- `.env` ist in `.gitignore` und wird nicht ins Repo gepusht.
- Lege niemals echte Keys in `README.md`, `.env.example` oder Source-Code ab.

## Python-Nutzung (ENV-only, ohne Key-Logging)

```python
from trading_bots.config import get_databento_api_key

api_key = get_databento_api_key()
# hier an deinen Databento-Client übergeben
```

Die Funktion liest nur `DATABENTO_API_KEY` aus der Umgebung und wirft einen klaren Fehler, falls der Key fehlt.
