"""
Сервис чтения и фильтрации сущностей Zep
Чтение узлов из графа Zep, фильтрация узлов, соответствующих предопределённым типам сущностей
"""

import json
import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from openai import OpenAI
from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_entity_reader')

# Для обобщённого типа возвращаемого значения
T = TypeVar('T')


@dataclass
class EntityNode:
    """Структура данных узла сущности"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # Информация о связанных рёбрах
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # Информация о связанных узлах
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        """Получение типа сущности (исключая метку Entity по умолчанию)"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Набор отфильтрованных сущностей"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    Сервис чтения и фильтрации сущностей Zep

    Основные функции:
    1. Чтение всех узлов из графа Zep
    2. Фильтрация узлов, соответствующих предопределённым типам сущностей (узлы, у которых Labels содержат не только Entity)
    3. Получение информации о связанных рёбрах и узлах для каждой сущности
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY не настроен")

        self.client = Zep(api_key=self.api_key)

    def _call_with_retry(
        self,
        func: Callable[[], T],
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """
        Вызов Zep API с механизмом повторных попыток

        Args:
            func: Выполняемая функция (lambda или callable без аргументов)
            operation_name: Название операции, используется в логах
            max_retries: Максимальное количество попыток (по умолчанию 3, т.е. максимум 3 попытки)
            initial_delay: Начальная задержка в секундах

        Returns:
            Результат вызова API
        """
        last_exception = None
        delay = initial_delay

        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} попытка {attempt + 1} не удалась: {str(e)[:100]}, "
                        f"повтор через {delay:.1f} сек..."
                    )
                    time.sleep(delay)
                    delay *= 2  # Экспоненциальная задержка
                else:
                    logger.error(f"Zep {operation_name} не удалось после {max_retries} попыток: {str(e)}")

        raise last_exception

    def _normalize_entity_names(self, entities: List['EntityNode']) -> None:
        """
        Нормализация имён сущностей — приведение к именительному падежу (кто? что?)
        и заглавной букве. Изменяет entity.name in-place.
        Использует один LLM-вызов для пакетной нормализации.
        """
        if not entities:
            return

        try:
            client = OpenAI(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL
            )
        except Exception as e:
            logger.warning(f"Не удалось создать LLM-клиент для нормализации: {e}")
            return

        names = [e.name for e in entities]
        names_json = json.dumps(names, ensure_ascii=False)

        prompt = f"""Приведи все имена сущностей к именительному падежу (кто? что?).
Также исправь стилистику: имена должны звучать как названия аккаунтов в социальных сетях — с заглавной буквы, лаконично.

Если имя — это страна или географический регион (например, «Исландия», «Великобритания»), верни его без изменений.
Если имя уже в именительном падеже и корректно — верни без изменений.
Если имя на английском — верни без изменений.

Примеры:
- «государственных служащих» → «Государственные служащие»
- «производственными работниками» → «Производственные работники»
- «депутатов Государственной Думы» → «Депутаты Государственной Думы»
- «офисных сотрудников» → «Офисные сотрудники»
- «Средний возраст» → «Работники среднего возраста»
- «профсоюзы» → «Профсоюзы»
- «IT-специалисты» → «IT-специалисты» (без изменений)
- «Молодёжь» → «Молодёжь» (без изменений)

Входные имена (JSON-массив):
{names_json}

Верни ТОЛЬКО JSON-массив с нормализованными именами в том же порядке и того же размера. Никакого другого текста."""

        try:
            response = client.chat.completions.create(
                model=Config.LLM_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "Ты — лингвистический ассистент. Отвечай только валидным JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=2000
            )

            content = response.choices[0].message.content.strip()
            # Убираем маркеры кода если есть
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3].strip()

            normalized = json.loads(content)

            if isinstance(normalized, list) and len(normalized) == len(entities):
                changed = 0
                for entity, new_name in zip(entities, normalized):
                    if isinstance(new_name, str) and new_name.strip() and new_name != entity.name:
                        logger.info(f"Нормализация имени: «{entity.name}» → «{new_name.strip()}»")
                        entity.name = new_name.strip()
                        changed += 1
                logger.info(f"Нормализация имён завершена: {changed} из {len(entities)} изменено")
            else:
                logger.warning(f"LLM вернул массив неверного размера, пропуск нормализации")

        except Exception as e:
            logger.warning(f"Ошибка нормализации имён сущностей: {e}, продолжаем без нормализации")

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Получение всех узлов графа (постраничное получение)

        Args:
            graph_id: Идентификатор графа

        Returns:
            Список узлов
        """
        logger.info(f"Получение всех узлов графа {graph_id}...")

        nodes = fetch_all_nodes(self.client, graph_id)

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })

        logger.info(f"Всего получено {len(nodes_data)} узлов")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Получение всех рёбер графа (постраничное получение)

        Args:
            graph_id: Идентификатор графа

        Returns:
            Список рёбер
        """
        logger.info(f"Получение всех рёбер графа {graph_id}...")

        edges = fetch_all_edges(self.client, graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })

        logger.info(f"Всего получено {len(edges_data)} рёбер")
        return edges_data

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        Получение всех связанных рёбер указанного узла (с механизмом повторных попыток)

        Args:
            node_uuid: UUID узла

        Returns:
            Список рёбер
        """
        try:
            # Вызов Zep API с механизмом повторных попыток
            edges = self._call_with_retry(
                func=lambda: self.client.graph.node.get_entity_edges(node_uuid=node_uuid),
                operation_name=f"получение рёбер узла(node={node_uuid[:8]}...)"
            )

            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })

            return edges_data
        except Exception as e:
            logger.warning(f"Не удалось получить рёбра узла {node_uuid}: {str(e)}")
            return []

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        Фильтрация узлов, соответствующих предопределённым типам сущностей

        Логика фильтрации:
        - Если Labels узла содержат только "Entity", значит эта сущность не соответствует предопределённым типам — пропускаем
        - Если Labels узла содержат метки помимо "Entity" и "Node", значит соответствует предопределённому типу — сохраняем

        Args:
            graph_id: Идентификатор графа
            defined_entity_types: Список предопределённых типов сущностей (необязательный, если указан — сохраняются только эти типы)
            enrich_with_edges: Получать ли информацию о связанных рёбрах для каждой сущности

        Returns:
            FilteredEntities: Набор отфильтрованных сущностей
        """
        logger.info(f"Начало фильтрации сущностей графа {graph_id}...")

        # Получение всех узлов
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)

        # Получение всех рёбер (для последующего поиска связей)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []

        # Построение маппинга UUID узла к данным узла
        node_map = {n["uuid"]: n for n in all_nodes}

        # Фильтрация сущностей, соответствующих условиям
        filtered_entities = []
        entity_types_found = set()

        for node in all_nodes:
            labels = node.get("labels", [])

            # Логика фильтрации: Labels должны содержать метки помимо "Entity" и "Node"
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]

            if not custom_labels:
                # Только метки по умолчанию — пропускаем
                continue

            # Если указаны предопределённые типы, проверяем соответствие
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            # Создание объекта узла сущности
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )

            # Получение связанных рёбер и узлов
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges

                # Получение базовой информации о связанных узлах
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })

                entity.related_nodes = related_nodes

            filtered_entities.append(entity)

        logger.info(f"Фильтрация завершена: всего узлов {total_count}, соответствующих условиям {len(filtered_entities)}, "
                   f"типы сущностей: {entity_types_found}")

        # Нормализация имён сущностей (именительный падеж, заглавная буква)
        self._normalize_entity_names(filtered_entities)

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        Получение одной сущности с полным контекстом (рёбра и связанные узлы, с механизмом повторных попыток)

        Args:
            graph_id: Идентификатор графа
            entity_uuid: UUID сущности

        Returns:
            EntityNode или None
        """
        try:
            # Получение узла с механизмом повторных попыток
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"получение деталей узла(uuid={entity_uuid[:8]}...)"
            )

            if not node:
                return None

            # Получение рёбер узла
            edges = self.get_node_edges(entity_uuid)

            # Получение всех узлов для поиска связей
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}

            # Обработка связанных рёбер и узлов
            related_edges = []
            related_node_uuids = set()

            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])

            # Получение информации о связанных узлах
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })

            return EntityNode(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )

        except Exception as e:
            logger.error(f"Не удалось получить сущность {entity_uuid}: {str(e)}")
            return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        Получение всех сущностей указанного типа

        Args:
            graph_id: Идентификатор графа
            entity_type: Тип сущности (например, "Student", "PublicFigure" и т.д.)
            enrich_with_edges: Получать ли информацию о связанных рёбрах

        Returns:
            Список сущностей
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities
