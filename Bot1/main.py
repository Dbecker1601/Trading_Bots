import os
import time
import logging
from forex_strategies.env_loader import load_project_env

load_project_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/app/logs/bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY", "")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
INTERVAL = int(os.getenv("INTERVAL_SECONDS", "60"))


def tick():
    # --- Hier kommt deine Trading-Logik rein ---
    pass


if __name__ == "__main__":
    if not DATABENTO_API_KEY:
        log.warning("DATABENTO_API_KEY ist nicht gesetzt!")
    log.info("Trading Bot gestartet (dry_run=%s, interval=%ds)", DRY_RUN, INTERVAL)
    while True:
        try:
            tick()
        except Exception as e:
            log.error("Fehler in tick(): %s", e)
        time.sleep(INTERVAL)
