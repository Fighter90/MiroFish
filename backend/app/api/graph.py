"""
API-маршруты для работы с графами
Используется механизм контекста проекта, состояние сохраняется на сервере
"""

import os
import traceback
import threading
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

# Получение логгера
logger = get_logger('mirofish.api')


def allowed_file(filename: str) -> bool:
    """Проверка допустимости расширения файла"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== Интерфейсы управления проектами ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    Получение деталей проекта
    """
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": f"Проект не найден: {project_id}"
        }), 404

    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    Список всех проектов
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)

    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    Удаление проекта
    """
    success = ProjectManager.delete_project(project_id)

    if not success:
        return jsonify({
            "success": False,
            "error": f"Проект не найден или не удалось удалить: {project_id}"
        }), 404

    return jsonify({
        "success": True,
        "message": f"Проект удалён: {project_id}"
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    Сброс состояния проекта (для повторного построения графа)
    """
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": f"Проект не найден: {project_id}"
        }), 404

    # Сброс до состояния «онтология сгенерирована»
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED

    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)

    return jsonify({
        "success": True,
        "message": f"Проект сброшен: {project_id}",
        "data": project.to_dict()
    })


# ============== Интерфейс 1: Загрузка файлов и генерация онтологии ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    Интерфейс 1: Загрузка файлов, анализ и генерация определения онтологии

    Способ запроса: multipart/form-data

    Параметры:
        files: загружаемые файлы (PDF/MD/TXT), возможна множественная загрузка
        simulation_requirement: описание требований к моделированию (обязательно)
        project_name: название проекта (необязательно)
        additional_context: дополнительное описание (необязательно)

    Ответ:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== Начало генерации определения онтологии ===")

        # Получение параметров
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')

        logger.debug(f"Название проекта: {project_name}")
        logger.debug(f"Требования к моделированию: {simulation_requirement[:100]}...")

        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Укажите описание требований к моделированию (simulation_requirement)"
            }), 400

        # Получение загруженных файлов
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": "Загрузите хотя бы один файл документа"
            }), 400

        # Создание проекта
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(f"Проект создан: {project.project_id}")

        # Сохранение файлов и извлечение текста
        document_texts = []
        all_text = ""

        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # Сохранение файла в директорию проекта
                file_info = ProjectManager.save_file_to_project(
                    project.project_id,
                    file,
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })

                # Извлечение текста
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": "Ни один документ не удалось обработать — проверьте формат файлов"
            }), 400

        # Сохранение извлечённого текста
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"Извлечение текста завершено, всего {len(all_text)} символов")

        # Генерация онтологии
        logger.info("Вызов LLM для генерации определения онтологии...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )

        # Сохранение онтологии в проект
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"Генерация онтологии завершена: {entity_count} типов сущностей, {edge_count} типов связей")

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== Генерация онтологии завершена === ID проекта: {project.project_id}")

        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Интерфейс 2: Построение графа ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    Интерфейс 2: Построение графа по project_id

    Запрос (JSON):
        {
            "project_id": "proj_xxxx",  // обязательно, из интерфейса 1
            "graph_name": "Название графа",    // необязательно
            "chunk_size": 500,          // необязательно, по умолчанию 500
            "chunk_overlap": 50         // необязательно, по умолчанию 50
        }

    Ответ:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "Задача построения графа запущена"
            }
        }
    """
    try:
        logger.info("=== Начало построения графа ===")

        # Проверка конфигурации
        errors = []
        if not Config.ZEP_API_KEY:
            errors.append("ZEP_API_KEY не настроен")
        if errors:
            logger.error(f"Ошибка конфигурации: {errors}")
            return jsonify({
                "success": False,
                "error": "Ошибка конфигурации: " + "; ".join(errors)
            }), 500

        # Разбор запроса
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"Параметры запроса: project_id={project_id}")

        if not project_id:
            return jsonify({
                "success": False,
                "error": "Укажите project_id"
            }), 400

        # Получение проекта
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Проект не найден: {project_id}"
            }), 404

        # Проверка состояния проекта
        force = data.get('force', False)  # Принудительное перестроение

        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": "Онтология проекта ещё не сгенерирована, сначала вызовите /ontology/generate"
            }), 400

        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "Граф строится, не отправляйте повторный запрос. Для принудительного перестроения добавьте force: true",
                "task_id": project.graph_build_task_id
            }), 400

        # Если принудительное перестроение — сброс состояния
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None

        # Получение настроек
        graph_name = data.get('graph_name', project.name or 'MiroFish Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)

        # Обновление настроек проекта
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap

        # Получение извлечённого текста
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": "Извлечённый текст не найден"
            }), 400

        # Получение онтологии
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": "Определение онтологии не найдено"
            }), 400

        # Создание асинхронной задачи
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"Построение графа: {graph_name}")
        logger.info(f"Создана задача построения графа: task_id={task_id}, project_id={project_id}")

        # Обновление состояния проекта
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)

        # Запуск фоновой задачи
        def build_task():
            build_logger = get_logger('mirofish.build')
            try:
                build_logger.info(f"[{task_id}] Начало построения графа...")
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    message="Инициализация сервиса построения графа..."
                )

                # Создание сервиса построения графа
                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)

                # Разбиение на фрагменты
                task_manager.update_task(
                    task_id,
                    message="Разбиение текста на фрагменты...",
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text,
                    chunk_size=chunk_size,
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)

                # Создание графа
                task_manager.update_task(
                    task_id,
                    message="Создание графа Zep...",
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)

                # Обновление graph_id проекта
                project.graph_id = graph_id
                ProjectManager.save_project(project)

                # Установка онтологии
                task_manager.update_task(
                    task_id,
                    message="Установка определения онтологии...",
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)

                # Добавление текста (сигнатура progress_callback: (msg, progress_ratio))
                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )

                task_manager.update_task(
                    task_id,
                    message=f"Начало добавления {total_chunks} текстовых фрагментов...",
                    progress=15
                )

                episode_uuids = builder.add_text_batches(
                    graph_id,
                    chunks,
                    batch_size=3,
                    progress_callback=add_progress_callback
                )

                # Ожидание завершения обработки Zep (проверка статуса processed для каждого episode)
                task_manager.update_task(
                    task_id,
                    message="Ожидание обработки данных Zep...",
                    progress=55
                )

                def wait_progress_callback(msg, progress_ratio):
                    progress = 55 + int(progress_ratio * 35)  # 55% - 90%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )

                builder._wait_for_episodes(episode_uuids, wait_progress_callback)

                # Получение данных графа
                task_manager.update_task(
                    task_id,
                    message="Получение данных графа...",
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)

                # Обновление состояния проекта
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)

                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] Построение графа завершено: graph_id={graph_id}, узлов={node_count}, рёбер={edge_count}")

                # Завершение
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="Построение графа завершено",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )

            except Exception as e:
                # Обновление состояния проекта на «ошибка»
                build_logger.error(f"[{task_id}] Ошибка построения графа: {str(e)}")
                build_logger.debug(traceback.format_exc())

                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=f"Ошибка построения: {str(e)}",
                    error=traceback.format_exc()
                )

        # Запуск фонового потока
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": "Задача построения графа запущена, отслеживайте прогресс через /task/{task_id}"
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Интерфейс запроса задач ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    Запрос состояния задачи
    """
    task = TaskManager().get_task(task_id)

    if not task:
        return jsonify({
            "success": False,
            "error": f"Задача не найдена: {task_id}"
        }), 404

    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    Список всех задач
    """
    tasks = TaskManager().list_tasks()

    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== Интерфейс данных графа ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    Получение данных графа (узлы и рёбра)
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY не настроен"
            }), 500

        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        graph_data = builder.get_graph_data(graph_id)

        return jsonify({
            "success": True,
            "data": graph_data
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    Удаление графа Zep
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY не настроен"
            }), 500

        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        builder.delete_graph(graph_id)

        return jsonify({
            "success": True,
            "message": f"Граф удалён: {graph_id}"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
