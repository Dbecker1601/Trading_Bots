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
from trading_bots.databento_client import create_databento_client

client = create_databento_client()
# client jetzt für Historical-Requests verwenden
```

Hinweise:
- `create_databento_client()` liest den Key intern über `DATABENTO_API_KEY`.
- Der Key wird nicht aus dem Code gelesen und nicht geloggt.
- Falls das Databento-SDK fehlt: `pip install databento`.
