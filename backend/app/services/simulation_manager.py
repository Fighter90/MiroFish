"""
Менеджер симуляций OASIS
Управление параллельными симуляциями на платформах Twitter и Reddit
Использование предустановленных скриптов + интеллектуальная генерация параметров конфигурации с помощью LLM
"""

import os
import json
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import ZepEntityReader, FilteredEntities
from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters

logger = get_logger('mirofish.simulation')


class SimulationStatus(str, Enum):
    """Статус симуляции"""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"      # Симуляция остановлена вручную
    COMPLETED = "completed"  # Симуляция завершена естественным образом
    FAILED = "failed"


class PlatformType(str, Enum):
    """Тип платформы"""
    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    """Состояние симуляции"""
    simulation_id: str
    project_id: str
    graph_id: str

    # Статус включения платформ
    enable_twitter: bool = True
    enable_reddit: bool = True

    # Статус
    status: SimulationStatus = SimulationStatus.CREATED

    # Данные этапа подготовки
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)

    # Информация о генерации конфигурации
    config_generated: bool = False
    config_reasoning: str = ""

    # Данные времени выполнения
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"

    # Временные метки
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Информация об ошибке
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Полный словарь состояния (для внутреннего использования)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }

    def to_simple_dict(self) -> Dict[str, Any]:
        """Упрощённый словарь состояния (для возврата через API)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "error": self.error,
        }


class SimulationManager:
    """
    Менеджер симуляций

    Основные функции:
    1. Чтение сущностей из графа Zep и их фильтрация
    2. Генерация OASIS Agent Profile
    3. Интеллектуальная генерация параметров конфигурации симуляции с помощью LLM
    4. Подготовка всех файлов, необходимых для предустановленных скриптов
    """

    # Каталог хранения данных симуляций
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../uploads/simulations'
    )

    def __init__(self):
        # Убедиться, что каталог существует
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)

        # Кэш состояний симуляций в памяти
        self._simulations: Dict[str, SimulationState] = {}

    def _get_simulation_dir(self, simulation_id: str) -> str:
        """Получить каталог данных симуляции"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir

    def _save_simulation_state(self, state: SimulationState):
        """Сохранить состояние симуляции в файл"""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")

        state.updated_at = datetime.now().isoformat()

        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)

        self._simulations[state.simulation_id] = state

    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """Загрузить состояние симуляции из файла"""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]

        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")

        if not os.path.exists(state_file):
            return None

        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )

        self._simulations[simulation_id] = state
        return state

    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
    ) -> SimulationState:
        """
        Создать новую симуляцию

        Args:
            project_id: ID проекта
            graph_id: ID графа Zep
            enable_twitter: Включить ли симуляцию Twitter
            enable_reddit: Включить ли симуляцию Reddit

        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"

        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
        )

        self._save_simulation_state(state)
        logger.info(f"Создана симуляция: {simulation_id}, project={project_id}, graph={graph_id}")

        return state

    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3
    ) -> SimulationState:
        """
        Подготовка среды симуляции (полностью автоматизированная)

        Этапы:
        1. Чтение и фильтрация сущностей из графа Zep
        2. Генерация OASIS Agent Profile для каждой сущности (опционально с LLM, поддержка параллельности)
        3. Интеллектуальная генерация параметров конфигурации симуляции с помощью LLM (время, активность, частота публикаций и т.д.)
        4. Сохранение файлов конфигурации и профилей
        5. Копирование предустановленных скриптов в каталог симуляции

        Args:
            simulation_id: ID симуляции
            simulation_requirement: Описание требований к симуляции (для генерации конфигурации LLM)
            document_text: Содержимое исходного документа (для понимания контекста LLM)
            defined_entity_types: Предопределённые типы сущностей (опционально)
            use_llm_for_profiles: Использовать ли LLM для генерации детальных персонажей
            progress_callback: Функция обратного вызова для отслеживания прогресса (stage, progress, message)
            parallel_profile_count: Количество параллельно генерируемых персонажей, по умолчанию 3

        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Симуляция не существует: {simulation_id}")

        try:
            state.status = SimulationStatus.PREPARING
            self._save_simulation_state(state)

            sim_dir = self._get_simulation_dir(simulation_id)

            # ========== Этап 1: Чтение и фильтрация сущностей ==========
            if progress_callback:
                progress_callback("reading", 0, "Подключение к графу Zep...")

            reader = ZepEntityReader()

            if progress_callback:
                progress_callback("reading", 30, "Чтение данных узлов...")

            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )

            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)

            if progress_callback:
                progress_callback(
                    "reading", 100,
                    f"Завершено, всего {filtered.filtered_count} сущностей",
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )

            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "Не найдено подходящих сущностей, проверьте правильность построения графа"
                self._save_simulation_state(state)
                return state

            # ========== Этап 2: Генерация Agent Profile ==========
            total_entities = len(filtered.entities)

            if progress_callback:
                progress_callback(
                    "generating_profiles", 0,
                    "Начало генерации...",
                    current=0,
                    total=total_entities
                )

            # Передаём graph_id для включения функции поиска Zep и получения более богатого контекста
            generator = OasisProfileGenerator(graph_id=state.graph_id)

            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles",
                        int(current / total * 100),
                        msg,
                        current=current,
                        total=total,
                        item_name=msg
                    )

            # Настройка пути для сохранения в реальном времени (приоритет формату Reddit JSON)
            realtime_output_path = None
            realtime_platform = "reddit"
            if state.enable_reddit:
                realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                realtime_platform = "reddit"
            elif state.enable_twitter:
                realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                realtime_platform = "twitter"

            profiles = generator.generate_profiles_from_entities(
                entities=filtered.entities,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                graph_id=state.graph_id,  # Передаём graph_id для поиска Zep
                parallel_count=parallel_profile_count,  # Количество параллельной генерации
                realtime_output_path=realtime_output_path,  # Путь для сохранения в реальном времени
                output_platform=realtime_platform  # Формат вывода
            )

            state.profiles_count = len(profiles)

            # Сохранение файлов профилей (Примечание: Twitter использует формат CSV, Reddit — формат JSON)
            # Reddit уже сохранён в реальном времени в процессе генерации, здесь сохраняем повторно для полноты
            if progress_callback:
                progress_callback(
                    "generating_profiles", 95,
                    "Сохранение файлов профилей...",
                    current=total_entities,
                    total=total_entities
                )

            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit"
                )

            if state.enable_twitter:
                # Twitter использует формат CSV! Это требование OASIS
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter"
                )

            if progress_callback:
                progress_callback(
                    "generating_profiles", 100,
                    f"Завершено, всего {len(profiles)} профилей",
                    current=len(profiles),
                    total=len(profiles)
                )

            # ========== Этап 3: Интеллектуальная генерация конфигурации симуляции с помощью LLM ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0,
                    "Анализ требований к симуляции...",
                    current=0,
                    total=3
                )

            config_generator = SimulationConfigGenerator()

            if progress_callback:
                progress_callback(
                    "generating_config", 30,
                    "Вызов LLM для генерации конфигурации...",
                    current=1,
                    total=3
                )

            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit
            )

            if progress_callback:
                progress_callback(
                    "generating_config", 70,
                    "Сохранение файла конфигурации...",
                    current=2,
                    total=3
                )

            # Сохранение файла конфигурации
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(sim_params.to_json())

            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning

            if progress_callback:
                progress_callback(
                    "generating_config", 100,
                    "Генерация конфигурации завершена",
                    current=3,
                    total=3
                )

            # Примечание: скрипты запуска остаются в каталоге backend/scripts/, больше не копируются в каталог симуляции
            # При запуске симуляции simulation_runner будет запускать скрипты из каталога scripts/

            # Обновление статуса
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)

            logger.info(f"Подготовка симуляции завершена: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")

            return state

        except Exception as e:
            logger.error(f"Ошибка подготовки симуляции: {simulation_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise

    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """Получить состояние симуляции"""
        return self._load_simulation_state(simulation_id)

    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """Получить список всех симуляций"""
        simulations = []

        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # Пропуск скрытых файлов (например, .DS_Store) и не-каталогов
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith('.') or not os.path.isdir(sim_path):
                    continue

                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)

        return simulations

    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> List[Dict[str, Any]]:
        """Получить Agent Profile симуляции"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Симуляция не существует: {simulation_id}")

        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(sim_dir, f"{platform}_profiles.json")

        if not os.path.exists(profile_path):
            return []

        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Получить конфигурацию симуляции"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")

        if not os.path.exists(config_path):
            return None

        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """Получить инструкции по запуску"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))

        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. Активировать среду conda: conda activate MiroFish\n"
                f"2. Запустить симуляцию (скрипты расположены в {scripts_dir}):\n"
                f"   - Запуск только Twitter: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - Запуск только Reddit: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - Параллельный запуск обеих платформ: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            )
        }
