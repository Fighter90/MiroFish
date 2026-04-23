"""
Сервис обновления графовой памяти Zep
Динамическое обновление графа Zep на основе активности Agent-ов в симуляции
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.locale import get_locale, set_locale

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Запись активности Agent-а"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str

    def to_episode_text(self) -> str:
        """
        Преобразование активности в текстовое описание для отправки в Zep

        Используется формат описания на естественном языке, чтобы Zep мог
        извлечь из него сущности и связи.
        Без добавления префиксов симуляции во избежание искажения обновления графа.
        """
        # Генерация описания в зависимости от типа действия
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }

        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()

        # Возвращаем формат "имя_агента: описание_активности" без префикса симуляции
        return f"{self.agent_name}: {description}"

    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"опубликовал пост: \u00ab{content}\u00bb"
        return "опубликовал пост"

    def _describe_like_post(self) -> str:
        """Лайк поста - включает текст поста и информацию об авторе"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")

        if post_content and post_author:
            return f"поставил лайк посту {post_author}: \u00ab{post_content}\u00bb"
        elif post_content:
            return f"поставил лайк посту: \u00ab{post_content}\u00bb"
        elif post_author:
            return f"поставил лайк посту пользователя {post_author}"
        return "поставил лайк посту"

    def _describe_dislike_post(self) -> str:
        """Дизлайк поста - включает текст поста и информацию об авторе"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")

        if post_content and post_author:
            return f"поставил дизлайк посту {post_author}: \u00ab{post_content}\u00bb"
        elif post_content:
            return f"поставил дизлайк посту: \u00ab{post_content}\u00bb"
        elif post_author:
            return f"поставил дизлайк посту пользователя {post_author}"
        return "поставил дизлайк посту"

    def _describe_repost(self) -> str:
        """Репост - включает содержимое оригинального поста и информацию об авторе"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")

        if original_content and original_author:
            return f"сделал репост поста {original_author}: \u00ab{original_content}\u00bb"
        elif original_content:
            return f"сделал репост поста: \u00ab{original_content}\u00bb"
        elif original_author:
            return f"сделал репост поста пользователя {original_author}"
        return "сделал репост поста"

    def _describe_quote_post(self) -> str:
        """Цитирование поста - включает содержимое оригинала, автора и комментарий"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")

        base = ""
        if original_content and original_author:
            base = f"процитировал пост {original_author} \u00ab{original_content}\u00bb"
        elif original_content:
            base = f"процитировал пост \u00ab{original_content}\u00bb"
        elif original_author:
            base = f"процитировал пост пользователя {original_author}"
        else:
            base = "процитировал пост"

        if quote_content:
            base += f" и прокомментировал: \u00ab{quote_content}\u00bb"
        return base

    def _describe_follow(self) -> str:
        """Подписка на пользователя - включает имя пользователя"""
        target_user_name = self.action_args.get("target_user_name", "")

        if target_user_name:
            return f"подписался на пользователя \u00ab{target_user_name}\u00bb"
        return "подписался на пользователя"

    def _describe_create_comment(self) -> str:
        """Создание комментария - включает текст комментария и информацию о посте"""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")

        if content:
            if post_content and post_author:
                return f"прокомментировал пост {post_author} \u00ab{post_content}\u00bb: \u00ab{content}\u00bb"
            elif post_content:
                return f"прокомментировал пост \u00ab{post_content}\u00bb: \u00ab{content}\u00bb"
            elif post_author:
                return f"прокомментировал пост {post_author}: \u00ab{content}\u00bb"
            return f"прокомментировал: \u00ab{content}\u00bb"
        return "оставил комментарий"

    def _describe_like_comment(self) -> str:
        """Лайк комментария - включает текст комментария и информацию об авторе"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")

        if comment_content and comment_author:
            return f"поставил лайк комментарию {comment_author}: \u00ab{comment_content}\u00bb"
        elif comment_content:
            return f"поставил лайк комментарию: \u00ab{comment_content}\u00bb"
        elif comment_author:
            return f"поставил лайк комментарию пользователя {comment_author}"
        return "поставил лайк комментарию"

    def _describe_dislike_comment(self) -> str:
        """Дизлайк комментария - включает текст комментария и информацию об авторе"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")

        if comment_content and comment_author:
            return f"поставил дизлайк комментарию {comment_author}: \u00ab{comment_content}\u00bb"
        elif comment_content:
            return f"поставил дизлайк комментарию: \u00ab{comment_content}\u00bb"
        elif comment_author:
            return f"поставил дизлайк комментарию пользователя {comment_author}"
        return "поставил дизлайк комментарию"

    def _describe_search(self) -> str:
        """Поиск постов - включает поисковый запрос"""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"искал \u00ab{query}\u00bb" if query else "выполнил поиск"

    def _describe_search_user(self) -> str:
        """Поиск пользователя - включает поисковый запрос"""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"искал пользователя \u00ab{query}\u00bb" if query else "искал пользователя"

    def _describe_mute(self) -> str:
        """Блокировка пользователя - включает имя заблокированного пользователя"""
        target_user_name = self.action_args.get("target_user_name", "")

        if target_user_name:
            return f"заблокировал пользователя \u00ab{target_user_name}\u00bb"
        return "заблокировал пользователя"

    def _describe_generic(self) -> str:
        # Для неизвестных типов действий генерируем общее описание
        return f"выполнил операцию {self.action_type}"


class ZepGraphMemoryUpdater:
    """
    Обновщик графовой памяти Zep

    Отслеживает файл логов actions симуляции и в реальном времени обновляет граф Zep
    новыми действиями агентов.
    Группирует по платформам, отправляет пакетами по BATCH_SIZE действий.

    Все значимые действия обновляются в Zep, action_args содержит полную контекстную информацию:
    - Оригинальный текст поста при лайке/дизлайке
    - Оригинальный текст поста при репосте/цитировании
    - Имя пользователя при подписке/блокировке
    - Оригинальный текст комментария при лайке/дизлайке
    """

    # Размер пакета (сколько действий накапливается перед отправкой для каждой платформы)
    BATCH_SIZE = 5

    # Отображаемые названия платформ (для консольного вывода)
    PLATFORM_DISPLAY_NAMES = {
        'twitter': 'Мир 1',
        'reddit': 'Мир 2',
    }

    # Интервал отправки (секунды), чтобы избежать слишком частых запросов
    SEND_INTERVAL = 0.5

    # Настройки повторных попыток
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # секунды

    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        Инициализация обновщика

        Args:
            graph_id: ID графа Zep
            api_key: Zep API Key (необязательно, по умолчанию берётся из конфигурации)
        """
        self.graph_id = graph_id
        self.api_key = api_key or Config.ZEP_API_KEY

        if not self.api_key:
            raise ValueError("ZEP_API_KEY не настроен")

        self.client = Zep(api_key=self.api_key)

        # Очередь активностей
        self._activity_queue: Queue = Queue()

        # Буфер активностей по платформам (каждая платформа накапливает до BATCH_SIZE перед пакетной отправкой)
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()

        # Управляющие флаги
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        # Статистика
        self._total_activities = 0  # Фактическое количество добавленных в очередь активностей
        self._total_sent = 0        # Количество успешно отправленных пакетов
        self._total_items_sent = 0  # Количество успешно отправленных активностей
        self._failed_count = 0      # Количество неудачных отправок пакетов
        self._skipped_count = 0     # Количество пропущенных активностей (DO_NOTHING)

        logger.info(f"ZepGraphMemoryUpdater инициализирован: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")

    def _get_platform_display_name(self, platform: str) -> str:
        """Получить отображаемое название платформы"""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)

    def start(self):
        """Запустить фоновый рабочий поток"""
        if self._running:
            return

        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(current_locale,),
            daemon=True,
            name=f"ZepMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"ZepGraphMemoryUpdater запущен: graph_id={self.graph_id}")

    def stop(self):
        """Остановить фоновый рабочий поток"""
        self._running = False

        # Отправить оставшиеся активности
        self._flush_remaining()

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)

        logger.info(f"ZepGraphMemoryUpdater остановлен: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")

    def add_activity(self, activity: AgentActivity):
        """
        Добавить активность агента в очередь

        Все значимые действия добавляются в очередь, включая:
        - CREATE_POST (публикация)
        - CREATE_COMMENT (комментарий)
        - QUOTE_POST (цитирование поста)
        - SEARCH_POSTS (поиск постов)
        - SEARCH_USER (поиск пользователя)
        - LIKE_POST/DISLIKE_POST (лайк/дизлайк поста)
        - REPOST (репост)
        - FOLLOW (подписка)
        - MUTE (блокировка)
        - LIKE_COMMENT/DISLIKE_COMMENT (лайк/дизлайк комментария)

        action_args содержит полную контекстную информацию (текст поста, имя пользователя и т.д.).

        Args:
            activity: Запись активности агента
        """
        # Пропуск действий типа DO_NOTHING
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return

        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"Активность добавлена в очередь Zep: {activity.agent_name} - {activity.action_type}")

    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        Добавить активность из словаря

        Args:
            data: Словарь, полученный из actions.jsonl
            platform: Название платформы (twitter/reddit)
        """
        # Пропуск записей типа event
        if "event_type" in data:
            return

        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )

        self.add_activity(activity)

    def _worker_loop(self):
        """Фоновый рабочий цикл - пакетная отправка активностей в Zep по платформам"""
        while self._running or not self._activity_queue.empty():
            try:
                # Попытка получить активность из очереди (таймаут 1 секунда)
                try:
                    activity = self._activity_queue.get(timeout=1)

                    # Добавление активности в буфер соответствующей платформы
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)

                        # Проверка, достигнут ли размер пакета для данной платформы
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # Отправка после снятия блокировки
                            self._send_batch_activities(batch, platform)
                            # Интервал отправки, чтобы избежать слишком частых запросов
                            time.sleep(self.SEND_INTERVAL)

                except Empty:
                    pass

            except Exception as e:
                logger.error(f"Исключение в рабочем цикле: {e}")
                time.sleep(1)

    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        Пакетная отправка активностей в граф Zep (объединение в один текст)

        Args:
            activities: Список активностей агентов
            platform: Название платформы
        """
        if not activities:
            return

        # Объединение нескольких активностей в один текст, разделённый переводами строк
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)

        # Отправка с повторными попытками
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )

                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(f"Успешно отправлен пакет из {len(activities)} активностей {display_name} в граф {self.graph_id}")
                logger.debug(f"Предпросмотр пакета: {combined_text[:200]}...")
                return

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Ошибка пакетной отправки в Zep (попытка {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Ошибка пакетной отправки в Zep после {self.MAX_RETRIES} попыток: {e}")
                    self._failed_count += 1

    def _flush_remaining(self):
        """Отправка оставшихся активностей из очереди и буфера"""
        # Сначала обработать оставшиеся активности из очереди, добавив их в буфер
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break

        # Затем отправить оставшиеся активности из буферов платформ (даже если их меньше BATCH_SIZE)
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(f"Отправка оставшихся {len(buffer)} активностей платформы {display_name}")
                    self._send_batch_activities(buffer, platform)
            # Очистка всех буферов
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}

        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # Общее количество добавленных в очередь активностей
            "batches_sent": self._total_sent,            # Количество успешно отправленных пакетов
            "items_sent": self._total_items_sent,        # Количество успешно отправленных активностей
            "failed_count": self._failed_count,          # Количество неудачных отправок
            "skipped_count": self._skipped_count,        # Количество пропущенных активностей (DO_NOTHING)
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # Размер буферов по платформам
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """
    Менеджер обновщиков графовой памяти Zep для нескольких симуляций

    Каждая симуляция может иметь свой экземпляр обновщика
    """

    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()

    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        """
        Создать обновщик графовой памяти для симуляции

        Args:
            simulation_id: ID симуляции
            graph_id: ID графа Zep

        Returns:
            Экземпляр ZepGraphMemoryUpdater
        """
        with cls._lock:
            # Если уже существует, сначала остановить старый
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()

            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater

            logger.info(f"Создан обновщик графовой памяти: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater

    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        """Получить обновщик симуляции"""
        return cls._updaters.get(simulation_id)

    @classmethod
    def stop_updater(cls, simulation_id: str):
        """Остановить и удалить обновщик симуляции"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"Обновщик графовой памяти остановлен: simulation_id={simulation_id}")

    # Флаг предотвращения повторного вызова stop_all
    _stop_all_done = False

    @classmethod
    def stop_all(cls):
        """Остановить все обновщики"""
        # Предотвращение повторного вызова
        if cls._stop_all_done:
            return
        cls._stop_all_done = True

        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"Ошибка остановки обновщика: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("Все обновщики графовой памяти остановлены")

    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Получить статистику всех обновщиков"""
        return {
            sim_id: updater.get_stats()
            for sim_id, updater in cls._updaters.items()
        }
