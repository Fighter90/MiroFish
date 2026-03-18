"""
Интеллектуальный генератор конфигурации симуляции
Использует LLM для автоматической генерации детальных параметров симуляции
на основе требований, содержимого документов и информации из графа знаний.
Полностью автоматизированный процесс, не требующий ручной настройки параметров.

Используется стратегия пошаговой генерации для избежания ошибок при генерации слишком длинного содержимого:
1. Генерация конфигурации времени
2. Генерация конфигурации событий
3. Пакетная генерация конфигурации агентов
4. Генерация конфигурации платформы
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.simulation_config')

# Конфигурация распорядка дня (московское время)
CHINA_TIMEZONE_CONFIG = {
    # Глубокая ночь (почти нет активности)
    "dead_hours": [0, 1, 2, 3, 4, 5],
    # Утренние часы (постепенное пробуждение)
    "morning_hours": [6, 7, 8],
    # Рабочие часы
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    # Вечерний пик (максимальная активность)
    "peak_hours": [19, 20, 21, 22],
    # Ночные часы (активность снижается)
    "night_hours": [23],
    # Коэффициенты активности
    "activity_multipliers": {
        "dead": 0.05,      # Ночью почти никого
        "morning": 0.4,    # Утром постепенно растёт активность
        "work": 0.7,       # Рабочее время — средняя активность
        "peak": 1.5,       # Вечерний пик
        "night": 0.5       # Поздняя ночь — снижение
    }
}


@dataclass
class AgentActivityConfig:
    """Конфигурация активности отдельного агента"""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str

    # Конфигурация активности (0.0-1.0)
    activity_level: float = 0.5  # Общий уровень активности

    # Частота публикаций (ожидаемое количество в час)
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0

    # Активные часы (24-часовой формат, 0-23)
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))

    # Скорость реакции (задержка реакции на горячие события, в модельных минутах)
    response_delay_min: int = 5
    response_delay_max: int = 60

    # Эмоциональный уклон (от -1.0 до 1.0, от негативного до позитивного)
    sentiment_bias: float = 0.0

    # Позиция (отношение к конкретной теме)
    stance: str = "neutral"  # supportive, opposing, neutral, observer

    # Вес влияния (определяет вероятность того, что публикации будут видны другим агентам)
    influence_weight: float = 1.0


@dataclass
class TimeSimulationConfig:
    """Конфигурация временной симуляции (на основе распорядка дня)"""
    # Общая продолжительность симуляции (в модельных часах)
    total_simulation_hours: int = 72  # По умолчанию 72 часа (3 дня)

    # Время, представляемое одним раундом (модельные минуты) — по умолчанию 60 минут (1 час), ускоренный поток времени
    minutes_per_round: int = 60

    # Диапазон количества агентов, активируемых в час
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20

    # Часы пик (вечер 19-22, время наибольшей активности)
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5

    # Часы минимальной активности (ночь 0-5, почти нет активности)
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Ночью активность крайне низкая

    # Утренние часы
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4

    # Рабочие часы
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class EventConfig:
    """Конфигурация событий"""
    # Начальные события (события, запускаемые при старте симуляции)
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)

    # Запланированные события (события, запускаемые в определённое время)
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)

    # Ключевые слова горячих тем
    hot_topics: List[str] = field(default_factory=list)

    # Направление развития общественного мнения
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """Конфигурация, специфичная для платформы"""
    platform: str  # twitter or reddit

    # Веса алгоритма рекомендаций
    recency_weight: float = 0.4  # Свежесть по времени
    popularity_weight: float = 0.3  # Популярность
    relevance_weight: float = 0.3  # Релевантность

    # Порог вирусного распространения (количество взаимодействий для запуска распространения)
    viral_threshold: int = 10

    # Сила эффекта эхо-камеры (степень группировки схожих мнений)
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Полная конфигурация параметров симуляции"""
    # Базовая информация
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str

    # Конфигурация времени
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)

    # Список конфигураций агентов
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)

    # Конфигурация событий
    event_config: EventConfig = field(default_factory=EventConfig)

    # Конфигурация платформ
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None

    # Конфигурация LLM
    llm_model: str = ""
    llm_base_url: str = ""

    # Метаданные генерации
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # Пояснение от LLM

    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }

    def to_json(self, indent: int = 2) -> str:
        """Преобразование в JSON-строку"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    Интеллектуальный генератор конфигурации симуляции

    Использует LLM для анализа требований к симуляции, содержимого документов
    и информации о сущностях графа знаний для автоматической генерации
    оптимальных параметров конфигурации симуляции.

    Используется стратегия пошаговой генерации:
    1. Генерация конфигурации времени и событий (легковесная)
    2. Пакетная генерация конфигурации агентов (по 10-20 за пакет)
    3. Генерация конфигурации платформы
    """

    # Максимальное количество символов контекста
    MAX_CONTEXT_LENGTH = 50000
    # Количество агентов в одном пакете
    AGENTS_PER_BATCH = 15

    # Длина усечения контекста для каждого шага (в символах)
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # Конфигурация времени
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # Конфигурация событий
    ENTITY_SUMMARY_LENGTH = 300          # Краткое описание сущности
    AGENT_SUMMARY_LENGTH = 300           # Краткое описание сущности в конфигурации агента
    ENTITIES_PER_TYPE_DISPLAY = 20       # Количество отображаемых сущностей каждого типа

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY не настроен")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """
        Интеллектуальная генерация полной конфигурации симуляции (пошаговая генерация)

        Args:
            simulation_id: Идентификатор симуляции
            project_id: Идентификатор проекта
            graph_id: Идентификатор графа знаний
            simulation_requirement: Описание требований к симуляции
            document_text: Исходный текст документа
            entities: Отфильтрованный список сущностей
            enable_twitter: Включить ли Twitter
            enable_reddit: Включить ли Reddit
            progress_callback: Функция обратного вызова прогресса (current_step, total_steps, message)

        Returns:
            SimulationParameters: Полные параметры симуляции
        """
        logger.info(f"Начало интеллектуальной генерации конфигурации симуляции: simulation_id={simulation_id}, кол-во сущностей={len(entities)}")

        # Вычисление общего количества шагов
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # Конфигурация времени + Конфигурация событий + N пакетов агентов + Конфигурация платформы
        current_step = 0

        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")

        # 1. Построение базового контекста
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities
        )

        reasoning_parts = []

        # ========== Шаг 1: Генерация конфигурации времени ==========
        report_progress(1, "Генерация конфигурации времени...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)
        reasoning_parts.append(f"Конфигурация времени: {time_config_result.get('reasoning', 'Успешно')}")

        # ========== Шаг 2: Генерация конфигурации событий ==========
        report_progress(2, "Генерация конфигурации событий и горячих тем...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"Конфигурация событий: {event_config_result.get('reasoning', 'Успешно')}")

        # ========== Шаги 3-N: Пакетная генерация конфигурации агентов ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]

            report_progress(
                3 + batch_idx,
                f"Генерация конфигурации агентов ({start_idx + 1}-{end_idx}/{len(entities)})..."
            )

            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement
            )
            all_agent_configs.extend(batch_configs)

        reasoning_parts.append(f"Конфигурация агентов: успешно сгенерировано {len(all_agent_configs)} шт.")

        # ========== Назначение авторов для начальных постов ==========
        logger.info("Назначение подходящих авторов-агентов для начальных постов...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(f"Назначение начальных постов: {assigned_count} постам назначены авторы")

        # ========== Последний шаг: Генерация конфигурации платформы ==========
        report_progress(total_steps, "Генерация конфигурации платформы...")
        twitter_config = None
        reddit_config = None

        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5
            )

        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6
            )

        # Построение итоговых параметров
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )

        logger.info(f"Генерация конфигурации симуляции завершена: {len(params.agent_configs)} конфигураций агентов")

        return params

    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode]
    ) -> str:
        """Построение контекста для LLM, усечённого до максимальной длины"""

        # Краткое описание сущностей
        entity_summary = self._summarize_entities(entities)

        # Построение контекста
        context_parts = [
            f"## Требования к симуляции\n{simulation_requirement}",
            f"\n## Информация о сущностях ({len(entities)} шт.)\n{entity_summary}",
        ]

        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # Оставляем запас в 500 символов

        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(документ усечён)"
            context_parts.append(f"\n## Исходное содержимое документа\n{doc_text}")

        return "\n".join(context_parts)

    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """Генерация краткого описания сущностей"""
        lines = []

        # Группировка по типу
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)

        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)} шт.)")
            # Использование настроенного количества отображения и длины описания
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... ещё {len(type_entities) - display_count} шт.")

        return "\n".join(lines)

    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """Вызов LLM с повторными попытками и логикой восстановления JSON"""
        import re

        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # С каждой попыткой снижаем температуру
                    # Не устанавливаем max_tokens, позволяя LLM генерировать свободно
                )

                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason

                # Проверка на усечение
                if finish_reason == 'length':
                    logger.warning(f"Вывод LLM усечён (попытка {attempt+1})")
                    content = self._fix_truncated_json(content)

                # Попытка разбора JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"Ошибка разбора JSON (попытка {attempt+1}): {str(e)[:80]}")

                    # Попытка восстановить JSON
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed

                    last_error = e

            except Exception as e:
                logger.warning(f"Ошибка вызова LLM (попытка {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))

        raise last_error or Exception("Не удалось вызвать LLM")

    def _fix_truncated_json(self, content: str) -> str:
        """Восстановление усечённого JSON"""
        content = content.strip()

        # Подсчёт незакрытых скобок
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')

        # Проверка на незакрытую строку
        if content and content[-1] not in '",}]':
            content += '"'

        # Закрытие скобок
        content += ']' * open_brackets
        content += '}' * open_braces

        return content

    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Попытка восстановления конфигурационного JSON"""
        import re

        # Восстановление усечённого содержимого
        content = self._fix_truncated_json(content)

        # Извлечение JSON-части
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()

            # Удаление переносов строк внутри строковых значений
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s

            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)

            try:
                return json.loads(json_str)
            except:
                # Попытка удаления всех управляющих символов
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass

        return None

    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        """Генерация конфигурации времени"""
        # Использование настроенной длины усечения контекста
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]

        # Вычисление максимально допустимого значения (80% агентов)
        max_agents_allowed = max(1, int(num_entities * 0.9))

        prompt = f"""На основе следующих требований к симуляции сгенерируйте конфигурацию временной симуляции.

{context_truncated}

## Задача
Создайте конфигурацию времени в формате JSON.

### Основные принципы (только для справки, необходимо гибко адаптировать под конкретное событие и группу участников):
- Целевая аудитория — русскоязычные пользователи, необходимо учитывать распорядок дня по московскому времени
- С 0 до 5 утра почти нет активности (коэффициент активности 0.05)
- С 6 до 8 утра активность постепенно растёт (коэффициент активности 0.4)
- Рабочее время 9-18 — средняя активность (коэффициент активности 0.7)
- Вечер 19-22 — пиковое время (коэффициент активности 1.5)
- После 23 активность снижается (коэффициент активности 0.5)
- Общая закономерность: ночью низкая активность, утром растёт, днём средняя, вечером пик
- **Важно**: приведённые примерные значения даны только для справки, вам нужно адаптировать конкретные временные интервалы в зависимости от характера события и особенностей группы участников
  - Например: пик студенческой аудитории может приходиться на 21-23; СМИ активны весь день; официальные учреждения — только в рабочее время
  - Например: внезапная горячая тема может вызвать обсуждения даже ночью, off_peak_hours можно соответственно сократить

### Формат возвращаемого JSON (без markdown)

Пример:
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "Пояснение к конфигурации времени для данного события"
}}

Описание полей:
- total_simulation_hours (int): Общая продолжительность симуляции, 24-168 часов, для внезапных событий короче, для длительных тем дольше
- minutes_per_round (int): Продолжительность раунда, 30-120 минут, рекомендуется 60 минут
- agents_per_hour_min (int): Минимальное количество активируемых агентов в час (диапазон: 1-{max_agents_allowed})
- agents_per_hour_max (int): Максимальное количество активируемых агентов в час (диапазон: 1-{max_agents_allowed})
- peak_hours (массив int): Часы пик, адаптируются под группу участников события
- off_peak_hours (массив int): Часы минимальной активности, обычно глубокая ночь
- morning_hours (массив int): Утренние часы
- work_hours (массив int): Рабочие часы
- reasoning (string): Краткое пояснение, почему выбрана такая конфигурация"""

        system_prompt = "Вы — эксперт по симуляции социальных сетей. Верните чистый JSON-формат, конфигурация времени должна соответствовать распорядку дня целевой аудитории."

        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Ошибка генерации конфигурации времени через LLM: {e}, переход на конфигурацию по умолчанию")
            return self._get_default_time_config(num_entities)

    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        """Получение конфигурации времени по умолчанию (стандартный распорядок дня)"""
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # 1 час на раунд, ускоренный поток времени
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "reasoning": "Используется конфигурация по умолчанию (1 час на раунд)"
        }

    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        """Разбор результата конфигурации времени с проверкой, что agents_per_hour не превышает общее количество агентов"""
        # Получение исходных значений
        agents_per_hour_min = result.get("agents_per_hour_min", max(1, num_entities // 15))
        agents_per_hour_max = result.get("agents_per_hour_max", max(5, num_entities // 5))

        # Проверка и корректировка: не должно превышать общее количество агентов
        if agents_per_hour_min > num_entities:
            logger.warning(f"agents_per_hour_min ({agents_per_hour_min}) превышает общее количество агентов ({num_entities}), скорректировано")
            agents_per_hour_min = max(1, num_entities // 10)

        if agents_per_hour_max > num_entities:
            logger.warning(f"agents_per_hour_max ({agents_per_hour_max}) превышает общее количество агентов ({num_entities}), скорректировано")
            agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)

        # Обеспечение min < max
        if agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max // 2)
            logger.warning(f"agents_per_hour_min >= max, скорректировано до {agents_per_hour_min}")

        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),  # По умолчанию 1 час на раунд
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,  # Ночью почти никого
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )

    def _generate_event_config(
        self,
        context: str,
        simulation_requirement: str,
        entities: List[EntityNode]
    ) -> Dict[str, Any]:
        """Генерация конфигурации событий"""

        # Получение списка доступных типов сущностей для справки LLM
        entity_types_available = list(set(
            e.get_entity_type() or "Unknown" for e in entities
        ))

        # Перечисление репрезентативных имён сущностей для каждого типа
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)

        type_info = "\n".join([
            f"- {t}: {', '.join(examples)}"
            for t, examples in type_examples.items()
        ])

        # Использование настроенной длины усечения контекста
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]

        prompt = f"""На основе следующих требований к симуляции сгенерируйте конфигурацию событий.

Требования к симуляции: {simulation_requirement}

{context_truncated}

## Доступные типы сущностей и примеры
{type_info}

## Задача
Создайте конфигурацию событий в формате JSON:
- Извлеките ключевые слова горячих тем
- Опишите направление развития общественного мнения
- Составьте содержимое начальных постов, **для каждого поста необходимо указать poster_type (тип автора)**

**Важно**: poster_type должен быть выбран из "Доступных типов сущностей" выше, чтобы начальные посты можно было назначить подходящим агентам для публикации.
Например: официальные заявления должны публиковаться типом Official/University, новости — типом MediaOutlet, мнения студентов — типом Student.

Формат возвращаемого JSON (без markdown):
{{
    "hot_topics": ["ключевое слово 1", "ключевое слово 2", ...],
    "narrative_direction": "<описание направления развития общественного мнения>",
    "initial_posts": [
        {{"content": "содержимое поста", "poster_type": "тип сущности (должен быть выбран из доступных типов)"}},
        ...
    ],
    "reasoning": "<краткое пояснение>"
}}"""

        system_prompt = "Вы — эксперт по анализу общественного мнения. Верните чистый JSON-формат. Обратите внимание: poster_type должен точно соответствовать доступным типам сущностей."

        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Ошибка генерации конфигурации событий через LLM: {e}, переход на конфигурацию по умолчанию")
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "Используется конфигурация по умолчанию"
            }

    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        """Разбор результата конфигурации событий"""
        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=[],
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", "")
        )

    def _assign_initial_post_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """
        Назначение подходящих авторов-агентов для начальных постов

        На основе poster_type каждого поста подбирается наиболее подходящий agent_id
        """
        if not event_config.initial_posts:
            return event_config

        # Построение индекса агентов по типу сущности
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)

        # Таблица соответствия типов (обработка различных форматов, которые может выдать LLM)
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }

        # Отслеживание использованных индексов агентов каждого типа для избежания повторного использования
        used_indices: Dict[str, int] = {}

        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")

            # Попытка найти подходящего агента
            matched_agent_id = None

            # 1. Прямое соответствие
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2. Соответствие через псевдонимы
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break

            # 3. Если всё ещё не найден, используется агент с наибольшим влиянием
            if matched_agent_id is None:
                logger.warning(f"Не найден агент типа '{poster_type}', используется агент с наибольшим влиянием")
                if agent_configs:
                    # Сортировка по влиянию, выбор наиболее влиятельного
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0

            updated_posts.append({
                "content": content,
                "poster_type": post.get("poster_type", "Unknown"),
                "poster_agent_id": matched_agent_id
            })

            logger.info(f"Назначение начального поста: poster_type='{poster_type}' -> agent_id={matched_agent_id}")

        event_config.initial_posts = updated_posts
        return event_config

    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """Пакетная генерация конфигурации агентов"""

        # Построение информации о сущностях (с использованием настроенной длины описания)
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else ""
            })

        prompt = f"""На основе следующей информации сгенерируйте конфигурацию активности в социальных сетях для каждой сущности.

Требования к симуляции: {simulation_requirement}

## Список сущностей
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## Задача
Сгенерируйте конфигурацию активности для каждой сущности, обратите внимание:
- **Время должно соответствовать распорядку дня**: с 0 до 5 ночи почти нет активности, вечером 19-22 — максимальная активность
- **Официальные учреждения** (University/GovernmentAgency): низкая активность (0.1-0.3), работают в рабочее время (9-17), медленная реакция (60-240 минут), высокое влияние (2.5-3.0)
- **СМИ** (MediaOutlet): средняя активность (0.4-0.6), активны весь день (8-23), быстрая реакция (5-30 минут), высокое влияние (2.0-2.5)
- **Физические лица** (Student/Person/Alumni): высокая активность (0.6-0.9), активны преимущественно вечером (18-23), быстрая реакция (1-15 минут), низкое влияние (0.8-1.2)
- **Публичные лица/эксперты**: средняя активность (0.4-0.6), средне-высокое влияние (1.5-2.0)

Формат возвращаемого JSON (без markdown):
{{
    "agent_configs": [
        {{
            "agent_id": <должен совпадать с входными данными>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <частота публикаций>,
            "comments_per_hour": <частота комментариев>,
            "active_hours": [<список активных часов, с учётом распорядка дня>],
            "response_delay_min": <минимальная задержка ответа в минутах>,
            "response_delay_max": <максимальная задержка ответа в минутах>,
            "sentiment_bias": <от -1.0 до 1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <вес влияния>
        }},
        ...
    ]
}}"""

        system_prompt = "Вы — эксперт по анализу поведения в социальных сетях. Верните чистый JSON, конфигурация должна соответствовать распорядку дня целевой аудитории."

        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"Ошибка генерации пакета конфигурации агентов через LLM: {e}, переход на генерацию по правилам")
            llm_configs = {}

        # Построение объектов AgentActivityConfig
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})

            # Если LLM не сгенерировал, используется генерация по правилам
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)

            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)

        return configs

    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """Генерация конфигурации отдельного агента на основе правил (стандартный распорядок дня)"""
        entity_type = (entity.get_entity_type() or "Unknown").lower()

        if entity_type in ["university", "governmentagency", "ngo"]:
            # Официальные учреждения: активны в рабочее время, низкая частота, высокое влияние
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # СМИ: активны весь день, средняя частота, высокое влияние
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # Эксперты/профессора: активны в рабочее время и вечером, средняя частота
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # Студенты: преимущественно вечером, высокая частота
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Утро + вечер
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # Выпускники: преимущественно вечером
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # Обеденный перерыв + вечер
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # Обычные пользователи: вечерний пик
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # День + вечер
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }

