"""
Скрипт предустановленной симуляции OASIS Twitter
Этот скрипт читает параметры из конфигурационного файла для выполнения симуляции, обеспечивая полную автоматизацию

Функциональные возможности:
- После завершения симуляции не закрывает среду сразу, переходит в режим ожидания команд
- Поддержка получения команд Interview через IPC
- Поддержка интервью отдельного Agent и пакетного интервью
- Поддержка удалённой команды закрытия среды

Использование:
    python run_twitter_simulation.py --config /path/to/simulation_config.json
    python run_twitter_simulation.py --config /path/to/simulation_config.json --no-wait  # Закрыть сразу после завершения
"""

import argparse
import asyncio
import json
import logging
import os
import random
import signal
import sys
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional

# Глобальные переменные: для обработки сигналов
_shutdown_event = None
_cleanup_done = False

# Добавление пути проекта
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_scripts_dir, '..'))
_project_root = os.path.abspath(os.path.join(_backend_dir, '..'))
sys.path.insert(0, _scripts_dir)
sys.path.insert(0, _backend_dir)

# Загрузка .env файла из корневого каталога проекта (содержит LLM_API_KEY и другие настройки)
from dotenv import load_dotenv
_env_file = os.path.join(_project_root, '.env')
if os.path.exists(_env_file):
    load_dotenv(_env_file)
else:
    _backend_env = os.path.join(_backend_dir, '.env')
    if os.path.exists(_backend_env):
        load_dotenv(_backend_env)


import re


class UnicodeFormatter(logging.Formatter):
    """Пользовательский форматировщик, преобразующий Unicode-последовательности в читаемые символы"""

    UNICODE_ESCAPE_PATTERN = re.compile(r'\\u([0-9a-fA-F]{4})')

    def format(self, record):
        result = super().format(record)

        def replace_unicode(match):
            try:
                return chr(int(match.group(1), 16))
            except (ValueError, OverflowError):
                return match.group(0)

        return self.UNICODE_ESCAPE_PATTERN.sub(replace_unicode, result)


class MaxTokensWarningFilter(logging.Filter):
    """Фильтрация предупреждений camel-ai о max_tokens (мы намеренно не устанавливаем max_tokens, позволяя модели решать самостоятельно)"""

    def filter(self, record):
        # Фильтрация логов, содержащих предупреждение о max_tokens
        if "max_tokens" in record.getMessage() and "Invalid or missing" in record.getMessage():
            return False
        return True


# Добавление фильтра при загрузке модуля, чтобы он действовал до выполнения кода camel
logging.getLogger().addFilter(MaxTokensWarningFilter())


def setup_oasis_logging(log_dir: str):
    """Настройка логирования OASIS, использование фиксированных имён лог-файлов"""
    os.makedirs(log_dir, exist_ok=True)

    # Очистка старых лог-файлов
    for f in os.listdir(log_dir):
        old_log = os.path.join(log_dir, f)
        if os.path.isfile(old_log) and f.endswith('.log'):
            try:
                os.remove(old_log)
            except OSError:
                pass

    formatter = UnicodeFormatter("%(levelname)s - %(asctime)s - %(name)s - %(message)s")

    loggers_config = {
        "social.agent": os.path.join(log_dir, "social.agent.log"),
        "social.twitter": os.path.join(log_dir, "social.twitter.log"),
        "social.rec": os.path.join(log_dir, "social.rec.log"),
        "oasis.env": os.path.join(log_dir, "oasis.env.log"),
        "table": os.path.join(log_dir, "table.log"),
    }

    for logger_name, log_file in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.propagate = False


try:
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    import oasis
    from oasis import (
        ActionType,
        LLMAction,
        ManualAction,
        generate_twitter_agent_graph
    )
except ImportError as e:
    print(f"Ошибка: не найдена зависимость {e}")
    print("Установите: pip install oasis-ai camel-ai")
    sys.exit(1)


# Константы, связанные с IPC
IPC_COMMANDS_DIR = "ipc_commands"
IPC_RESPONSES_DIR = "ipc_responses"
ENV_STATUS_FILE = "env_status.json"

class CommandType:
    """Константы типов команд"""
    INTERVIEW = "interview"
    BATCH_INTERVIEW = "batch_interview"
    CLOSE_ENV = "close_env"


class IPCHandler:
    """Обработчик IPC-команд"""

    def __init__(self, simulation_dir: str, env, agent_graph):
        self.simulation_dir = simulation_dir
        self.env = env
        self.agent_graph = agent_graph
        self.commands_dir = os.path.join(simulation_dir, IPC_COMMANDS_DIR)
        self.responses_dir = os.path.join(simulation_dir, IPC_RESPONSES_DIR)
        self.status_file = os.path.join(simulation_dir, ENV_STATUS_FILE)
        self._running = True

        # Убедиться, что каталоги существуют
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def update_status(self, status: str):
        """Обновить состояние среды"""
        with open(self.status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

    def poll_command(self) -> Optional[Dict[str, Any]]:
        """Опрос для получения ожидающих обработки команд"""
        if not os.path.exists(self.commands_dir):
            return None

        # Получение файлов команд (отсортированных по времени)
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))

        command_files.sort(key=lambda x: x[1])

        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

        return None

    def send_response(self, command_id: str, status: str, result: Dict = None, error: str = None):
        """Отправить ответ"""
        response = {
            "command_id": command_id,
            "status": status,
            "result": result,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }

        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response, f, ensure_ascii=False, indent=2)

        # Удаление файла команды
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass

    async def handle_interview(self, command_id: str, agent_id: int, prompt: str) -> bool:
        """
        Обработка команды интервью отдельного Agent

        Returns:
            True -- успех, False -- ошибка
        """
        try:
            # Получение Agent
            agent = self.agent_graph.get_agent(agent_id)

            # Создание действия Interview
            interview_action = ManualAction(
                action_type=ActionType.INTERVIEW,
                action_args={"prompt": prompt}
            )

            # Выполнение Interview
            actions = {agent: interview_action}
            await self.env.step(actions)

            # Получение результата из базы данных
            result = self._get_interview_result(agent_id)

            self.send_response(command_id, "completed", result=result)
            print(f"  Interview завершён: agent_id={agent_id}")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"  Ошибка Interview: agent_id={agent_id}, error={error_msg}")
            self.send_response(command_id, "failed", error=error_msg)
            return False

    async def handle_batch_interview(self, command_id: str, interviews: List[Dict]) -> bool:
        """
        Обработка команды пакетного интервью

        Args:
            interviews: [{"agent_id": int, "prompt": str}, ...]
        """
        try:
            # Построение словаря действий
            actions = {}
            agent_prompts = {}  # Запись prompt каждого agent

            for interview in interviews:
                agent_id = interview.get("agent_id")
                prompt = interview.get("prompt", "")

                try:
                    agent = self.agent_graph.get_agent(agent_id)
                    actions[agent] = ManualAction(
                        action_type=ActionType.INTERVIEW,
                        action_args={"prompt": prompt}
                    )
                    agent_prompts[agent_id] = prompt
                except Exception as e:
                    print(f"  Предупреждение: не удалось получить Agent {agent_id}: {e}")

            if not actions:
                self.send_response(command_id, "failed", error="Нет доступных Agent")
                return False

            # Выполнение пакетного Interview
            await self.env.step(actions)

            # Получение всех результатов
            results = {}
            for agent_id in agent_prompts.keys():
                result = self._get_interview_result(agent_id)
                results[agent_id] = result

            self.send_response(command_id, "completed", result={
                "interviews_count": len(results),
                "results": results
            })
            print(f"  Пакетный Interview завершён: {len(results)} Agent")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"  Ошибка пакетного Interview: {error_msg}")
            self.send_response(command_id, "failed", error=error_msg)
            return False

    def _get_interview_result(self, agent_id: int) -> Dict[str, Any]:
        """Получить последний результат Interview из базы данных"""
        db_path = os.path.join(self.simulation_dir, "twitter_simulation.db")

        result = {
            "agent_id": agent_id,
            "response": None,
            "timestamp": None
        }

        if not os.path.exists(db_path):
            return result

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Запрос последней записи Interview
            cursor.execute("""
                SELECT user_id, info, created_at
                FROM trace
                WHERE action = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (ActionType.INTERVIEW.value, agent_id))

            row = cursor.fetchone()
            if row:
                user_id, info_json, created_at = row
                try:
                    info = json.loads(info_json) if info_json else {}
                    result["response"] = info.get("response", info)
                    result["timestamp"] = created_at
                except json.JSONDecodeError:
                    result["response"] = info_json

            conn.close()

        except Exception as e:
            print(f"  Ошибка чтения результата Interview: {e}")

        return result

    async def process_commands(self) -> bool:
        """
        Обработка всех ожидающих команд

        Returns:
            True -- продолжить работу, False -- завершить
        """
        command = self.poll_command()
        if not command:
            return True

        command_id = command.get("command_id")
        command_type = command.get("command_type")
        args = command.get("args", {})

        print(f"\nПолучена IPC-команда: {command_type}, id={command_id}")

        if command_type == CommandType.INTERVIEW:
            await self.handle_interview(
                command_id,
                args.get("agent_id", 0),
                args.get("prompt", "")
            )
            return True

        elif command_type == CommandType.BATCH_INTERVIEW:
            await self.handle_batch_interview(
                command_id,
                args.get("interviews", [])
            )
            return True

        elif command_type == CommandType.CLOSE_ENV:
            print("Получена команда закрытия среды")
            self.send_response(command_id, "completed", result={"message": "Среда будет закрыта"})
            return False

        else:
            self.send_response(command_id, "failed", error=f"Неизвестный тип команды: {command_type}")
            return True


class TwitterSimulationRunner:
    """Исполнитель симуляции Twitter"""

    # Доступные действия Twitter (не включая INTERVIEW, INTERVIEW может быть вызван только вручную через ManualAction)
    AVAILABLE_ACTIONS = [
        ActionType.CREATE_POST,
        ActionType.LIKE_POST,
        ActionType.REPOST,
        ActionType.FOLLOW,
        ActionType.DO_NOTHING,
        ActionType.QUOTE_POST,
    ]

    def __init__(self, config_path: str, wait_for_commands: bool = True):
        """
        Инициализация исполнителя симуляции

        Args:
            config_path: Путь к файлу конфигурации (simulation_config.json)
            wait_for_commands: Ожидать ли команды после завершения симуляции (по умолчанию True)
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.simulation_dir = os.path.dirname(config_path)
        self.wait_for_commands = wait_for_commands
        self.env = None
        self.agent_graph = None
        self.ipc_handler = None

    def _load_config(self) -> Dict[str, Any]:
        """Загрузка файла конфигурации"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _get_profile_path(self) -> str:
        """Получить путь к файлу Profile (OASIS Twitter использует формат CSV)"""
        return os.path.join(self.simulation_dir, "twitter_profiles.csv")

    def _get_db_path(self) -> str:
        """Получить путь к базе данных"""
        return os.path.join(self.simulation_dir, "twitter_simulation.db")

    def _create_model(self):
        """
        Создание модели LLM

        Единое использование конфигурации из файла .env в корневом каталоге проекта (наивысший приоритет):
        - LLM_API_KEY: API-ключ
        - LLM_BASE_URL: Базовый URL API
        - LLM_MODEL_NAME: Название модели
        """
        # Приоритетное чтение конфигурации из .env
        llm_api_key = os.environ.get("LLM_API_KEY", "")
        llm_base_url = os.environ.get("LLM_BASE_URL", "")
        llm_model = os.environ.get("LLM_MODEL_NAME", "")

        # Если в .env нет, использовать config как запасной вариант
        if not llm_model:
            llm_model = self.config.get("llm_model", "gpt-4o-mini")

        # Установка переменных окружения, необходимых для camel-ai
        if llm_api_key:
            os.environ["OPENAI_API_KEY"] = llm_api_key

        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("API Key не указан. Задайте LLM_API_KEY в файле .env в корне проекта")

        if llm_base_url:
            os.environ["OPENAI_API_BASE_URL"] = llm_base_url

        print(f"Конфигурация LLM: model={llm_model}, base_url={llm_base_url[:40] if llm_base_url else 'по умолчанию'}...")

        return ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=llm_model,
        )

    def _get_active_agents_for_round(
        self,
        env,
        current_hour: int,
        round_num: int
    ) -> List:
        """
        Определение активных Agent для текущего раунда на основе времени и конфигурации

        Args:
            env: Среда OASIS
            current_hour: Текущий симулируемый час (0-23)
            round_num: Текущий номер раунда

        Returns:
            Список активных Agent
        """
        time_config = self.config.get("time_config", {})
        agent_configs = self.config.get("agent_configs", [])

        # Базовое количество активаций
        base_min = time_config.get("agents_per_hour_min", 5)
        base_max = time_config.get("agents_per_hour_max", 20)

        # Корректировка по временному периоду
        peak_hours = time_config.get("peak_hours", [9, 10, 11, 14, 15, 20, 21, 22])
        off_peak_hours = time_config.get("off_peak_hours", [0, 1, 2, 3, 4, 5])

        if current_hour in peak_hours:
            multiplier = time_config.get("peak_activity_multiplier", 1.5)
        elif current_hour in off_peak_hours:
            multiplier = time_config.get("off_peak_activity_multiplier", 0.3)
        else:
            multiplier = 1.0

        target_count = int(random.uniform(base_min, base_max) * multiplier)

        # Расчёт вероятности активации на основе конфигурации каждого Agent
        candidates = []
        for cfg in agent_configs:
            agent_id = cfg.get("agent_id", 0)
            active_hours = cfg.get("active_hours", list(range(8, 23)))
            activity_level = cfg.get("activity_level", 0.5)

            # Проверка, находится ли в активном времени
            if current_hour not in active_hours:
                continue

            # Расчёт вероятности по уровню активности
            if random.random() < activity_level:
                candidates.append(agent_id)

        # Случайный выбор
        selected_ids = random.sample(
            candidates,
            min(target_count, len(candidates))
        ) if candidates else []

        # Преобразование в объекты Agent
        active_agents = []
        for agent_id in selected_ids:
            try:
                agent = env.agent_graph.get_agent(agent_id)
                active_agents.append((agent_id, agent))
            except Exception:
                pass

        return active_agents

    async def run(self, max_rounds: int = None):
        """Запуск симуляции Twitter

        Args:
            max_rounds: Максимальное количество раундов симуляции (необязательно, для ограничения слишком длинной симуляции)
        """
        print("=" * 60)
        print("Симуляция OASIS Twitter")
        print(f"Файл конфигурации: {self.config_path}")
        print(f"ID симуляции: {self.config.get('simulation_id', 'unknown')}")
        print(f"Режим ожидания команд: {'включён' if self.wait_for_commands else 'выключен'}")
        print("=" * 60)

        # Загрузка конфигурации времени
        time_config = self.config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)

        # Расчёт общего количества раундов
        total_rounds = (total_hours * 60) // minutes_per_round

        # Если указано максимальное количество раундов, то обрезать
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                print(f"\nРаунды ограничены: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")

        print(f"\nПараметры симуляции:")
        print(f"  - Общая длительность симуляции: {total_hours} часов")
        print(f"  - Время на раунд: {minutes_per_round} минут")
        print(f"  - Всего раундов: {total_rounds}")
        if max_rounds:
            print(f"  - Макс. число раундов: {max_rounds}")
        print(f"  - Количество Agent: {len(self.config.get('agent_configs', []))}")

        # Создание модели
        print("\nИнициализация модели LLM...")
        model = self._create_model()

        # Загрузка графа Agent
        print("Загрузка Agent Profile...")
        profile_path = self._get_profile_path()
        if not os.path.exists(profile_path):
            print(f"Ошибка: файл Profile не найден: {profile_path}")
            return

        self.agent_graph = await generate_twitter_agent_graph(
            profile_path=profile_path,
            model=model,
            available_actions=self.AVAILABLE_ACTIONS,
        )

        # Путь к базе данных
        db_path = self._get_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Удалена старая база данных: {db_path}")

        # Создание среды
        print("Создание среды OASIS...")
        self.env = oasis.make(
            agent_graph=self.agent_graph,
            platform=oasis.DefaultPlatformType.TWITTER,
            database_path=db_path,
            semaphore=30,  # Ограничение максимального количества параллельных LLM-запросов для предотвращения перегрузки API
        )

        await self.env.reset()
        print("Инициализация среды завершена\n")

        # Инициализация обработчика IPC
        self.ipc_handler = IPCHandler(self.simulation_dir, self.env, self.agent_graph)
        self.ipc_handler.update_status("running")

        # Выполнение начальных событий
        event_config = self.config.get("event_config", {})
        initial_posts = event_config.get("initial_posts", [])

        if initial_posts:
            print(f"Выполнение начальных событий ({len(initial_posts)} начальных постов)...")
            initial_actions = {}
            for post in initial_posts:
                agent_id = post.get("poster_agent_id", 0)
                content = post.get("content", "")
                try:
                    agent = self.env.agent_graph.get_agent(agent_id)
                    initial_actions[agent] = ManualAction(
                        action_type=ActionType.CREATE_POST,
                        action_args={"content": content}
                    )
                except Exception as e:
                    print(f"  Предупреждение: не удалось создать начальный пост для Agent {agent_id}: {e}")

            if initial_actions:
                await self.env.step(initial_actions)
                print(f"  Опубликовано {len(initial_actions)} начальных постов")

        # Основной цикл симуляции
        print("\nНачало цикла симуляции...")
        start_time = datetime.now()

        for round_num in range(total_rounds):
            # Расчёт текущего времени симуляции
            simulated_minutes = round_num * minutes_per_round
            simulated_hour = (simulated_minutes // 60) % 24
            simulated_day = simulated_minutes // (60 * 24) + 1

            # Получение активных Agent для текущего раунда
            active_agents = self._get_active_agents_for_round(
                self.env, simulated_hour, round_num
            )

            if not active_agents:
                continue

            # Построение действий
            actions = {
                agent: LLMAction()
                for _, agent in active_agents
            }

            # Выполнение действий
            await self.env.step(actions)

            # Вывод прогресса
            if (round_num + 1) % 10 == 0 or round_num == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                progress = (round_num + 1) / total_rounds * 100
                print(f"  [Day {simulated_day}, {simulated_hour:02d}:00] "
                      f"Round {round_num + 1}/{total_rounds} ({progress:.1f}%) "
                      f"- {len(active_agents)} agents active "
                      f"- elapsed: {elapsed:.1f}s")

        total_elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\nЦикл симуляции завершён!")
        print(f"  - Общее время: {total_elapsed:.1f} сек")
        print(f"  - База данных: {db_path}")

        # Переход в режим ожидания команд
        if self.wait_for_commands:
            print("\n" + "=" * 60)
            print("Переход в режим ожидания команд - среда продолжает работать")
            print("Поддерживаемые команды: interview, batch_interview, close_env")
            print("=" * 60)

            self.ipc_handler.update_status("alive")

            # Цикл ожидания команд (используется глобальный _shutdown_event)
            try:
                while not _shutdown_event.is_set():
                    should_continue = await self.ipc_handler.process_commands()
                    if not should_continue:
                        break
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=0.5)
                        break  # Получен сигнал выхода
                    except asyncio.TimeoutError:
                        pass
            except KeyboardInterrupt:
                print("\nПолучен сигнал прерывания")
            except asyncio.CancelledError:
                print("\nЗадача отменена")
            except Exception as e:
                print(f"\nОшибка обработки команды: {e}")

            print("\nЗакрытие среды...")

        # Закрытие среды
        self.ipc_handler.update_status("stopped")
        await self.env.close()

        print("Среда закрыта")
        print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description='Симуляция OASIS Twitter')
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Путь к файлу конфигурации (simulation_config.json)'
    )
    parser.add_argument(
        '--max-rounds',
        type=int,
        default=None,
        help='Макс. число раундов (ограничить длительность симуляции)'
    )
    parser.add_argument(
        '--no-wait',
        action='store_true',
        default=False,
        help='Закрыть среду сразу после симуляции, без ожидания команд'
    )

    args = parser.parse_args()

    # Создание события shutdown в начале функции main
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    if not os.path.exists(args.config):
        print(f"Ошибка: файл конфигурации не найден: {args.config}")
        sys.exit(1)

    # Инициализация конфигурации логирования (с фиксированными именами файлов, очистка старых логов)
    simulation_dir = os.path.dirname(args.config) or "."
    setup_oasis_logging(os.path.join(simulation_dir, "log"))

    runner = TwitterSimulationRunner(
        config_path=args.config,
        wait_for_commands=not args.no_wait
    )
    await runner.run(max_rounds=args.max_rounds)


def setup_signal_handlers():
    """
    Настройка обработчиков сигналов, обеспечивающих корректный выход при получении SIGTERM/SIGINT
    Даёт программе возможность нормально очистить ресурсы (закрыть базу данных, среду и т.д.)
    """
    def signal_handler(signum, frame):
        global _cleanup_done
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\nПолучен сигнал {sig_name}, завершение работы...")
        if not _cleanup_done:
            _cleanup_done = True
            if _shutdown_event:
                _shutdown_event.set()
        else:
            # Принудительный выход только при повторном получении сигнала
            print("Принудительный выход...")
            sys.exit(1)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
    setup_signal_handlers()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПрограмма прервана")
    except SystemExit:
        pass
    finally:
        print("Процесс симуляции завершён")
