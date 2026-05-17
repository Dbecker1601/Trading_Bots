# trading-bot1 Container

Der Container wird aus diesem Verzeichnis gebaut und installiert dauerhaft im Image:

- Node.js 22 und npm
- Codex CLI
- Claude Code CLI
- Ollama CLI
- Python-Abhaengigkeiten aus `requirements.txt`

Persistente Daten liegen in Mounts/Volumes:

- Projekt: `./:/app`
- Logs: `./logs:/app/logs`
- CLI-Konfigurationen: `trading-bot1-home:/root`
- Ollama-Modelle: `trading-bot1-ollama:/root/.ollama`

## Neu bauen und starten

```bash
cd /opt/trading-bot/bots/bot1
docker compose build
docker compose up -d --force-recreate
```

## In den Container gehen

```bash
docker compose exec trading-bot bash
```

## Ollama nutzen

Wenn du den Ollama-Server im Container brauchst:

```bash
docker compose exec trading-bot bash
ollama serve
```

In einem zweiten Terminal:

```bash
docker compose exec trading-bot bash
ollama pull llama3.1
```

Nicht `docker compose down -v` ausfuehren, wenn Home-Config oder Ollama-Modelle erhalten bleiben sollen.
