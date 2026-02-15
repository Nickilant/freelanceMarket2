import logging
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
SERVICE_FEE = int(os.getenv("SERVICE_FEE", "5"))
SUPPORTED_CURRENCIES = ["TON", "USDT"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def validate_config() -> None:
    """Проверка обязательной конфигурации окружения."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not CRYPTOBOT_TOKEN:
        missing.append("CRYPTOBOT_TOKEN")

    if missing:
        raise RuntimeError(f"Не заданы обязательные переменные окружения: {', '.join(missing)}")
