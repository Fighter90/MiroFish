"""
Механизм повторных попыток вызова API
Обработка повторных вызовов внешних API (LLM и др.)
"""

import time
import random
import functools
from typing import Callable, Any, Optional, Type, Tuple
from ..utils.logger import get_logger

logger = get_logger('mirofish.retry')


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Декоратор повторных попыток с экспоненциальным откатом

    Args:
        max_retries: Максимальное количество повторов
        initial_delay: Начальная задержка (секунды)
        max_delay: Максимальная задержка (секунды)
        backoff_factor: Коэффициент отката
        jitter: Добавлять ли случайное отклонение
        exceptions: Типы исключений для повторных попыток
        on_retry: Функция обратного вызова при повторе (exception, retry_count)

    Usage:
        @retry_with_backoff(max_retries=3)
        def call_llm_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(f"Функция {func.__name__} не удалась после {max_retries} повторов: {str(e)}")
                        raise

                    # Расчёт задержки
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())

                    logger.warning(
                        f"Функция {func.__name__} попытка {attempt + 1} не удалась: {str(e)}, "
                        f"повтор через {current_delay:.1f} сек..."
                    )

                    if on_retry:
                        on_retry(e, attempt + 1)

                    time.sleep(current_delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper
    return decorator


def retry_with_backoff_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Асинхронная версия декоратора повторных попыток
    """
    import asyncio

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(f"Асинхронная функция {func.__name__} не удалась после {max_retries} повторов: {str(e)}")
                        raise

                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())

                    logger.warning(
                        f"Асинхронная функция {func.__name__} попытка {attempt + 1} не удалась: {str(e)}, "
                        f"повтор через {current_delay:.1f} сек..."
                    )

                    if on_retry:
                        on_retry(e, attempt + 1)

                    await asyncio.sleep(current_delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper
    return decorator


class RetryableAPIClient:
    """
    Обёртка API-клиента с повторными попытками
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def call_with_retry(
        self,
        func: Callable,
        *args,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        **kwargs
    ) -> Any:
        """
        Вызов функции с повторными попытками при ошибке

        Args:
            func: Вызываемая функция
            *args: Аргументы функции
            exceptions: Типы исключений для повторных попыток
            **kwargs: Именованные аргументы функции

        Returns:
            Возвращаемое значение функции
        """
        last_exception = None
        delay = self.initial_delay

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)

            except exceptions as e:
                last_exception = e

                if attempt == self.max_retries:
                    logger.error(f"Вызов API не удался после {self.max_retries} повторов: {str(e)}")
                    raise

                current_delay = min(delay, self.max_delay)
                current_delay = current_delay * (0.5 + random.random())

                logger.warning(
                    f"Вызов API попытка {attempt + 1} не удалась: {str(e)}, "
                    f"повтор через {current_delay:.1f} сек..."
                )

                time.sleep(current_delay)
                delay *= self.backoff_factor

        raise last_exception

    def call_batch_with_retry(
        self,
        items: list,
        process_func: Callable,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        continue_on_failure: bool = True
    ) -> Tuple[list, list]:
        """
        Пакетный вызов с отдельными повторами для каждого элемента

        Args:
            items: Список элементов для обработки
            process_func: Функция обработки, принимающая один элемент
            exceptions: Типы исключений для повторных попыток
            continue_on_failure: Продолжать ли обработку при ошибке отдельного элемента

        Returns:
            (список успешных результатов, список ошибок)
        """
        results = []
        failures = []

        for idx, item in enumerate(items):
            try:
                result = self.call_with_retry(
                    process_func,
                    item,
                    exceptions=exceptions
                )
                results.append(result)

            except Exception as e:
                logger.error(f"Обработка элемента {idx + 1} не удалась: {str(e)}")
                failures.append({
                    "index": idx,
                    "item": item,
                    "error": str(e)
                })

                if not continue_on_failure:
                    raise

        return results, failures
