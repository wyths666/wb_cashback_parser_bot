import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import os

LOG_DIR = "/app/logs"
LOG_FILE = "app.log"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILE)

os.makedirs(LOG_DIR, exist_ok=True)

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

file_handler = TimedRotatingFileHandler(
    filename=LOG_PATH,
    when="D",
    interval=7,
    backupCount=4,
    encoding="utf-8",
    utc=True,
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(formatter)
stdout_handler.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()
root_logger.addHandler(file_handler)
root_logger.addHandler(stdout_handler)

bot_logger = logging.getLogger("bot")
parser_logger = logging.getLogger("parser")
scheduler_logger = logging.getLogger("scheduler")
