"""
Модуль конфигурации логирования
Единое управление логами с выводом в консоль и файл
"""

import os
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler


def _ensure_utf8_stdout():
    """
    Обеспечение кодировки UTF-8 для stdout/stderr
    Решение проблемы отображения символов в консоли Windows
    """
    if sys.platform == 'win32':
        # Перенастройка стандартного вывода на UTF-8 в Windows
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# Директория логов
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')


def setup_logger(name: str = 'mirofish', level: int = logging.DEBUG) -> logging.Logger:
    """
    Настройка логгера

    Args:
        name: Имя логгера
        level: Уровень логирования

    Returns:
        Настроенный логгер
    """
    # Создание директории логов
    os.makedirs(LOG_DIR, exist_ok=True)

    # Создание логгера
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Отключение распространения логов к корневому logger для избежания дублирования
    logger.propagate = False

    # Если обработчики уже добавлены — не дублировать
    if logger.handlers:
        return logger

    # Форматы логов
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )

    # 1. Файловый обработчик — подробные логи (по дате, с ротацией)
    log_filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_filename),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # 2. Консольный обработчик — краткие логи (INFO и выше)
    # Обеспечение кодировки UTF-8 в Windows
    _ensure_utf8_stdout()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # Добавление обработчиков
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = 'mirofish') -> logging.Logger:
    """
    Получение логгера (создание при отсутствии)

    Args:
        name: Имя логгера

    Returns:
        Экземпляр логгера
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# Создание логгера по умолчанию
logger = setup_logger()


# Вспомогательные методы
def debug(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)

def info(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)

def critical(msg, *args, **kwargs):
    logger.critical(msg, *args, **kwargs)
