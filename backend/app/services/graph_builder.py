"""
Сервис построения графа
Интерфейс 2: Построение Standalone Graph с использованием Zep API
"""

import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from zep_cloud.client import Zep
from zep_cloud import EpisodeData, EntityEdgeSourceTarget

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from .text_processor import TextProcessor
from ..utils.locale import t, get_locale, set_locale

logger = get_logger('mirofish.graph_builder')


@dataclass
class GraphInfo:
    """Информация о графе"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Сервис построения графа
    Отвечает за вызов Zep API для построения графа знаний
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY не настроен")

        self.client = Zep(api_key=self.api_key)
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        Асинхронное построение графа

        Args:
            text: Входной текст
            ontology: Определение онтологии (выход интерфейса 1)
            graph_name: Название графа
            chunk_size: Размер текстового блока
            chunk_overlap: Размер перекрытия блоков
            batch_size: Количество блоков в каждой партии

        Returns:
            ID задачи
        """
        # Создание задачи
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )

        # Захват локали из request-context перед стартом фонового потока
        # (определение потерялось в -X ours merge upstream i18n-рефакторинга).
        current_locale = get_locale()

        # Выполнение построения в фоновом потоке
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, current_locale)
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        locale: str = 'ru'
    ):
        """Рабочий поток построения графа"""
        set_locale(locale)
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Начало построения графа..."
            )

            # 1. Создание графа
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"Граф создан: {graph_id}"
            )

            # 2. Установка онтологии
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="Онтология установлена"
            )

            # 3. Разбиение текста на блоки
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"Текст разделён на {total_chunks} блоков"
            )

            # 4. Пакетная отправка данных
            episode_uuids = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.4),  # 20-60%
                    message=msg
                )
            )

            # 5. Ожидание завершения обработки Zep
            self.task_manager.update_task(
                task_id,
                progress=60,
                message="Ожидание обработки данных Zep..."
            )

            self._wait_for_episodes(
                episode_uuids,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 0.3),  # 60-90%
                    message=msg
                )
            )

            # 6. Получение информации о графе
            self.task_manager.update_task(
                task_id,
                progress=90,
                message="Получение информации о графе..."
            )

            graph_info = self._get_graph_info(graph_id)

            # Завершение
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)

    def create_graph(self, name: str) -> str:
        """Создание графа Zep (публичный метод)"""
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"

        self.client.graph.create(
            graph_id=graph_id,
            name=name,
            description="MiroFish Social Simulation Graph"
        )

        return graph_id

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """Установка онтологии графа (публичный метод)"""
        import warnings
        from typing import Optional
        from pydantic import Field
        from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel

        # Подавление предупреждений Pydantic v2 о Field(default=None)
        # Это требуемое использование Zep SDK, предупреждения возникают при динамическом создании классов и могут быть безопасно проигнорированы
        warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')

        # Зарезервированные имена Zep, которые нельзя использовать как имена атрибутов
        RESERVED_NAMES = {'uuid', 'name', 'group_id', 'name_embedding', 'summary', 'created_at'}

        def safe_attr_name(attr_name: str) -> str:
            """Преобразование зарезервированных имён в безопасные"""
            if attr_name.lower() in RESERVED_NAMES:
                return f"entity_{attr_name}"
            return attr_name

        # Динамическое создание типов сущностей
        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")

            # Создание словаря атрибутов и аннотаций типов (требуется для Pydantic v2)
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in entity_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # Использование безопасного имени
                attr_desc = attr_def.get("description", attr_name)
                # Zep API требует description в Field, это обязательно
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[EntityText]  # Аннотация типа

            attrs["__annotations__"] = annotations

            # Динамическое создание класса
            entity_class = type(name, (EntityModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class

        # Динамическое создание типов рёбер
        edge_definitions = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")

            # Создание словаря атрибутов и аннотаций типов
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in edge_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # Использование безопасного имени
                attr_desc = attr_def.get("description", attr_name)
                # Zep API требует description в Field, это обязательно
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[str]  # Для атрибутов рёбер используется тип str

            attrs["__annotations__"] = annotations

            # Динамическое создание класса
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            edge_class = type(class_name, (EdgeModel,), attrs)
            edge_class.__doc__ = description

            # Построение source_targets
            source_targets = []
            for st in edge_def.get("source_targets", []):
                source_targets.append(
                    EntityEdgeSourceTarget(
                        source=st.get("source", "Entity"),
                        target=st.get("target", "Entity")
                    )
                )

            if source_targets:
                edge_definitions[name] = (edge_class, source_targets)

        # Вызов Zep API для установки онтологии
        if entity_types or edge_definitions:
            self.client.graph.set_ontology(
                graph_ids=[graph_id],
                entities=entity_types if entity_types else None,
                edges=edge_definitions if edge_definitions else None,
            )

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Пакетное добавление текста в граф, возвращает список uuid всех episode"""
        episode_uuids = []
        total_chunks = len(chunks)

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size

            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    f"Отправка партии {batch_num}/{total_batches} ({len(batch_chunks)} блоков)...",
                    progress
                )

            # Построение данных episode
            episodes = [
                EpisodeData(data=chunk, type="text")
                for chunk in batch_chunks
            ]

            # Отправка в Zep
            try:
                batch_result = self.client.graph.add_batch(
                    graph_id=graph_id,
                    episodes=episodes
                )

                # Сбор возвращённых uuid episode
                if batch_result and isinstance(batch_result, list):
                    for ep in batch_result:
                        ep_uuid = getattr(ep, 'uuid_', None) or getattr(ep, 'uuid', None)
                        if ep_uuid:
                            episode_uuids.append(ep_uuid)

                # Избежание слишком частых запросов
                time.sleep(1)

            except Exception as e:
                if progress_callback:
                    progress_callback(f"Ошибка отправки партии {batch_num}: {str(e)}", 0)
                raise

        return episode_uuids

    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600
    ):
        """Ожидание завершения обработки всех episode (через проверку статуса processed каждого episode)"""
        if not episode_uuids:
            if progress_callback:
                progress_callback("Ожидание не требуется (нет episode)", 1.0)
            return

        start_time = time.time()
        pending_episodes = set(episode_uuids)
        completed_count = 0
        total_episodes = len(episode_uuids)

        if progress_callback:
            progress_callback(f"Начало ожидания обработки {total_episodes} текстовых блоков...", 0)

        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        f"Тайм-аут для части текстовых блоков, завершено {completed_count}/{total_episodes}",
                        completed_count / total_episodes
                    )
                break

            # Проверка статуса обработки каждого episode
            for ep_uuid in list(pending_episodes):
                try:
                    episode = self.client.graph.episode.get(uuid_=ep_uuid)
                    is_processed = getattr(episode, 'processed', False)

                    if is_processed:
                        pending_episodes.remove(ep_uuid)
                        completed_count += 1

                except Exception as e:
                    # Игнорирование ошибок отдельных запросов, продолжение
                    pass

            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    f"Обработка Zep... {completed_count}/{total_episodes} завершено, {len(pending_episodes)} в ожидании ({elapsed} сек)",
                    completed_count / total_episodes if total_episodes > 0 else 0
                )

            if pending_episodes:
                time.sleep(3)  # Проверка каждые 3 секунды

        if progress_callback:
            progress_callback(f"Обработка завершена: {completed_count}/{total_episodes}", 1.0)

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """Получение информации о графе"""
        # Получение узлов (с пагинацией)
        nodes = fetch_all_nodes(self.client, graph_id)

        # Получение рёбер (с пагинацией)
        edges = fetch_all_edges(self.client, graph_id)

        # Подсчёт типов сущностей
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Получение полных данных графа (с подробной информацией)

        Args:
            graph_id: ID графа

        Returns:
            Словарь с узлами и рёбрами, включая временную информацию, атрибуты и другие подробные данные
        """
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        # Создание маппинга узлов для получения имён узлов
        node_map = {}
        for node in nodes:
            node_uuid = getattr(node, 'uuid_', None) or getattr(node, 'uuid', '')
            if node_uuid:
                node_map[node_uuid] = node.name or ""

        nodes_data = []
        for node in nodes:
            try:
                # Получение времени создания
                created_at = getattr(node, 'created_at', None)
                if created_at:
                    created_at = str(created_at)

                node_uuid = getattr(node, 'uuid_', None) or getattr(node, 'uuid', '')
                nodes_data.append({
                    "uuid": node_uuid,
                    "name": node.name or "",
                    "labels": node.labels or [],
                    "summary": node.summary or "",
                    "attributes": node.attributes or {},
                    "created_at": created_at,
                })
            except Exception as e:
                logger.warning(f"Ошибка обработки узла: {e}")
                continue

        edges_data = []
        for edge in edges:
            try:
                # Получение временной информации
                created_at = getattr(edge, 'created_at', None)
                valid_at = getattr(edge, 'valid_at', None)
                invalid_at = getattr(edge, 'invalid_at', None)
                expired_at = getattr(edge, 'expired_at', None)

                # Получение episodes
                episodes = getattr(edge, 'episodes', None) or getattr(edge, 'episode_ids', None)
                if episodes and not isinstance(episodes, list):
                    episodes = [str(episodes)]
                elif episodes:
                    episodes = [str(e) for e in episodes]

                # Получение fact_type
                fact_type = getattr(edge, 'fact_type', None) or edge.name or ""

                edge_uuid = getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', '')
                edges_data.append({
                    "uuid": edge_uuid,
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "fact_type": fact_type,
                    "source_node_uuid": edge.source_node_uuid or "",
                    "target_node_uuid": edge.target_node_uuid or "",
                    "source_node_name": node_map.get(edge.source_node_uuid, ""),
                    "target_node_name": node_map.get(edge.target_node_uuid, ""),
                    "attributes": edge.attributes or {},
                    "created_at": str(created_at) if created_at else None,
                    "valid_at": str(valid_at) if valid_at else None,
                    "invalid_at": str(invalid_at) if invalid_at else None,
                    "expired_at": str(expired_at) if expired_at else None,
                    "episodes": episodes or [],
                })
            except Exception as e:
                logger.warning(f"Ошибка обработки ребра: {e}")
                continue

        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, graph_id: str):
        """Удаление графа"""
        self.client.graph.delete(graph_id=graph_id)
