"""
Модуль IPC для симуляции
Межпроцессное взаимодействие между бэкендом Flask и скриптом симуляции

Реализация простого паттерна команда/ответ через файловую систему:
1. Flask записывает команду в каталог commands/
2. Скрипт симуляции опрашивает каталог команд, выполняет команду и записывает ответ в каталог responses/
3. Flask опрашивает каталог ответов для получения результатов
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.logger import get_logger

logger = get_logger('mirofish.simulation_ipc')


class CommandType(str, Enum):
    """Тип команды"""
    INTERVIEW = "interview"           # Интервью с одним агентом
    BATCH_INTERVIEW = "batch_interview"  # Пакетное интервью
    CLOSE_ENV = "close_env"           # Закрытие среды


class CommandStatus(str, Enum):
    """Статус команды"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """IPC-команда"""
    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCCommand':
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class IPCResponse:
    """IPC-ответ"""
    command_id: str
    status: CommandStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCResponse':
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class SimulationIPCClient:
    """
    IPC-клиент симуляции (используется на стороне Flask)

    Отправляет команды процессу симуляции и ожидает ответы
    """

    def __init__(self, simulation_dir: str):
        """
        Инициализация IPC-клиента

        Args:
            simulation_dir: Каталог данных симуляции
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")

        # Создание каталогов, если они не существуют
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5
    ) -> IPCResponse:
        """
        Отправка команды и ожидание ответа

        Args:
            command_type: Тип команды
            args: Параметры команды
            timeout: Тайм-аут (секунды)
            poll_interval: Интервал опроса (секунды)

        Returns:
            IPCResponse

        Raises:
            TimeoutError: Тайм-аут ожидания ответа
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args
        )

        # Запись файла команды
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        with open(command_file, 'w', encoding='utf-8') as f:
            json.dump(command.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"Отправлена IPC-команда: {command_type.value}, command_id={command_id}")

        # Ожидание ответа
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', encoding='utf-8') as f:
                        response_data = json.load(f)
                    response = IPCResponse.from_dict(response_data)

                    # Очистка файлов команды и ответа
                    try:
                        os.remove(command_file)
                        os.remove(response_file)
                    except OSError:
                        pass

                    logger.info(f"Получен IPC-ответ: command_id={command_id}, status={response.status.value}")
                    return response
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Ошибка разбора ответа: {e}")

            time.sleep(poll_interval)

        # Тайм-аут
        logger.error(f"Тайм-аут ожидания IPC-ответа: command_id={command_id}")

        # Очистка файла команды
        try:
            os.remove(command_file)
        except OSError:
            pass

        raise TimeoutError(f"Тайм-аут ожидания ответа на команду ({timeout} сек)")

    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> IPCResponse:
        """
        Отправка команды интервью с одним агентом

        Args:
            agent_id: ID агента
            prompt: Вопрос интервью
            platform: Указание платформы (необязательно)
                - "twitter": Интервью только на платформе Twitter
                - "reddit": Интервью только на платформе Reddit
                - None: При двухплатформенной симуляции — интервью на обеих платформах, при одноплатформенной — на данной платформе
            timeout: Тайм-аут

        Returns:
            IPCResponse, поле result содержит результаты интервью
        """
        args = {
            "agent_id": agent_id,
            "prompt": prompt
        }
        if platform:
            args["platform"] = platform

        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> IPCResponse:
        """
        Отправка команды пакетного интервью

        Args:
            interviews: Список интервью, каждый элемент содержит {"agent_id": int, "prompt": str, "platform": str (необязательно)}
            platform: Платформа по умолчанию (необязательно, перекрывается значением platform в каждом элементе интервью)
                - "twitter": По умолчанию интервью только на платформе Twitter
                - "reddit": По умолчанию интервью только на платформе Reddit
                - None: При двухплатформенной симуляции каждый агент интервьюируется на обеих платформах
            timeout: Тайм-аут

        Returns:
            IPCResponse, поле result содержит все результаты интервью
        """
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform

        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """
        Отправка команды закрытия среды

        Args:
            timeout: Тайм-аут

        Returns:
            IPCResponse
        """
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout
        )

    def check_env_alive(self) -> bool:
        """
        Проверка активности среды симуляции

        Определяется по файлу env_status.json
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        if not os.path.exists(status_file):
            return False

        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return status.get("status") == "alive"
        except (json.JSONDecodeError, OSError):
            return False


class SimulationIPCServer:
    """
    IPC-сервер симуляции (используется на стороне скрипта симуляции)

    Опрашивает каталог команд, выполняет команды и возвращает ответы
    """

    def __init__(self, simulation_dir: str):
        """
        Инициализация IPC-сервера

        Args:
            simulation_dir: Каталог данных симуляции
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")

        # Создание каталогов, если они не существуют
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

        # Статус среды
        self._running = False

    def start(self):
        """Отметить сервер как работающий"""
        self._running = True
        self._update_env_status("alive")

    def stop(self):
        """Отметить сервер как остановленный"""
        self._running = False
        self._update_env_status("stopped")

    def _update_env_status(self, status: str):
        """Обновление файла статуса среды"""
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

    def poll_commands(self) -> Optional[IPCCommand]:
        """
        Опрос каталога команд, возврат первой ожидающей обработки команды

        Returns:
            IPCCommand или None
        """
        if not os.path.exists(self.commands_dir):
            return None

        # Получение файлов команд, отсортированных по времени
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))

        command_files.sort(key=lambda x: x[1])

        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return IPCCommand.from_dict(data)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Ошибка чтения файла команды: {filepath}, {e}")
                continue

        return None

    def send_response(self, response: IPCResponse):
        """
        Отправка ответа

        Args:
            response: IPC-ответ
        """
        response_file = os.path.join(self.responses_dir, f"{response.command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, ensure_ascii=False, indent=2)

        # Удаление файла команды
        command_file = os.path.join(self.commands_dir, f"{response.command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass

    def send_success(self, command_id: str, result: Dict[str, Any]):
        """Отправка успешного ответа"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result
        ))

    def send_error(self, command_id: str, error: str):
        """Отправка ответа с ошибкой"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error
        ))
