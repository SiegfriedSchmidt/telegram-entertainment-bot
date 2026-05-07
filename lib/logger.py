from io import BytesIO
import colorama
from colorama import Fore
from collections import deque
import logging
import sys
from lib.utils.general_utils import get_file_from_str


class COLORS:
    DEBUG = Fore.LIGHTGREEN_EX
    INFO = Fore.LIGHTWHITE_EX
    WARNING = Fore.YELLOW
    ERROR = Fore.RED
    CRITICAL = Fore.LIGHTRED_EX


def get_one_format(color, app_name, app_color):
    return f"{Fore.LIGHTWHITE_EX}%(asctime)s - {app_color}{app_name}{Fore.LIGHTWHITE_EX} - {color}%(levelname)s{Fore.LIGHTWHITE_EX} - %(message)s{Fore.RESET}"


def get_formats(app_name, app_color):
    return {
        logging.DEBUG: get_one_format(COLORS.DEBUG, app_name, app_color),
        logging.INFO: get_one_format(COLORS.INFO, app_name, app_color),
        logging.WARNING: get_one_format(COLORS.WARNING, app_name, app_color),
        logging.ERROR: get_one_format(COLORS.ERROR, app_name, app_color),
        logging.CRITICAL: get_one_format(COLORS.CRITICAL, app_name, app_color),
    }


class ColoredFormatter(logging.Formatter):
    def __init__(self, app_name, app_color):
        super().__init__()
        self.formats = get_formats(app_name, app_color)

    def format(self, record):
        log_fmt = self.formats.get(record.levelno)
        formatter = logging.Formatter(log_fmt, "%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


class PlainFormatter(logging.Formatter):
    def __init__(self, app_name):
        fmt = f"%(asctime)s - {app_name} - %(levelname)s - %(message)s"
        super().__init__(fmt, "%Y-%m-%d %H:%M:%S")


class LogStream:
    def __init__(self):
        self.logs: deque[str] = deque(maxlen=100)

    def write(self, string: str):
        if string.strip():
            self.logs.append(string)

    def flush(self):
        pass

    def get_file(self) -> BytesIO:
        return get_file_from_str(str(self), 'logs.txt')

    def __str__(self):
        return "".join(self.logs)

    def __bool__(self):
        return bool(self.logs)


def create_logger(name: str, app_name: str, logger_log_stream: LogStream, app_color: str):
    colorama.init()

    # Init logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Create handlers
    terminal_handler = logging.StreamHandler(sys.stdout)
    log_stream_handler = logging.StreamHandler(logger_log_stream)

    # Set formatters
    terminal_handler.setFormatter(ColoredFormatter(app_name, app_color))
    log_stream_handler.setFormatter(PlainFormatter(app_name))

    # Add handlers
    logger.addHandler(terminal_handler)
    logger.addHandler(log_stream_handler)

    return logger


log_stream = LogStream()

main_logger = create_logger('LOGGER', 'LOGGER', log_stream, Fore.MAGENTA)
peewee_logger = create_logger('peewee', 'SQL', log_stream, Fore.LIGHTBLUE_EX)
ledger_logger = create_logger('ledger', 'LEDGER', log_stream, Fore.LIGHTCYAN_EX)

if __name__ == '__main__':
    pass
