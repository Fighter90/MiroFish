"""
API-маршруты отчётов
Предоставляет интерфейсы для генерации, получения и обсуждения отчётов моделирования
"""

import os
import traceback
import threading
from flask import request, jsonify, send_file

from . import report_bp
from ..config import Config
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager
from ..models.project import ProjectManager
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.report')


# ============== Интерфейс генерации отчётов ==============

@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """
    Генерация отчёта по анализу моделирования (асинхронная задача)

    Это длительная операция, интерфейс немедленно возвращает task_id,
    используйте GET /api/report/generate/status для запроса прогресса

    Запрос (JSON):
        {
            "simulation_id": "sim_xxxx",    // обязательно, ID моделирования
            "force_regenerate": false        // необязательно, принудительная повторная генерация
        }

    Ответ:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",
                "status": "generating",
                "message": "Задача генерации отчёта запущена"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Укажите simulation_id"
            }), 400

        force_regenerate = data.get('force_regenerate', False)

        # Получение информации о моделировании
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"Моделирование не найдено: {simulation_id}"
            }), 404

        # Проверка наличия существующего отчёта
        if not force_regenerate:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "message": "Отчёт уже существует",
                        "already_generated": True
                    }
                })

        # Получение информации о проекте
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Проект не найден: {state.project_id}"
            }), 404

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Нет ID графа — убедитесь, что граф построен"
            }), 400

        simulation_requirement = project.simulation_requirement
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Не указано описание требований к моделированию"
            }), 400

        # Предварительная генерация report_id для немедленного возврата фронтенду
        import uuid
        report_id = f"report_{uuid.uuid4().hex[:12]}"

        # Создание асинхронной задачи
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="report_generate",
            metadata={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "report_id": report_id
            }
        )

        # Определение фоновой задачи
        def run_generate():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="Инициализация Report Agent..."
                )

                # Создание Report Agent
                agent = ReportAgent(
                    graph_id=graph_id,
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement
                )

                # Callback прогресса
                def progress_callback(stage, progress, message):
                    task_manager.update_task(
                        task_id,
                        progress=progress,
                        message=f"[{stage}] {message}"
                    )

                # Генерация отчёта (передаём предварительно сгенерированный report_id)
                report = agent.generate_report(
                    progress_callback=progress_callback,
                    report_id=report_id
                )

                # Сохранение отчёта
                ReportManager.save_report(report)

                if report.status == ReportStatus.COMPLETED:
                    task_manager.complete_task(
                        task_id,
                        result={
                            "report_id": report.report_id,
                            "simulation_id": simulation_id,
                            "status": "completed"
                        }
                    )
                else:
                    task_manager.fail_task(task_id, report.error or "Ошибка генерации отчёта")

            except Exception as e:
                logger.error(f"Ошибка генерации отчёта: {str(e)}")
                task_manager.fail_task(task_id, str(e))

        # Запуск фонового потока
        thread = threading.Thread(target=run_generate, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "report_id": report_id,
                "task_id": task_id,
                "status": "generating",
                "message": "Задача генерации отчёта запущена, проверяйте прогресс через /api/report/generate/status",
                "already_generated": False
            }
        })

    except Exception as e:
        logger.error(f"Ошибка запуска задачи генерации отчёта: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/generate/status', methods=['POST'])
def get_generate_status():
    """
    Запрос прогресса задачи генерации отчёта

    Запрос (JSON):
        {
            "task_id": "task_xxxx",         // необязательно, task_id, возвращённый generate
            "simulation_id": "sim_xxxx"     // необязательно, ID моделирования
        }

    Ответ:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|failed",
                "progress": 45,
                "message": "..."
            }
        }
    """
    try:
        data = request.get_json() or {}

        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')

        # Если указан simulation_id, сначала проверяем наличие завершённого отчёта
        if simulation_id:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "progress": 100,
                        "message": "Отчёт сгенерирован",
                        "already_completed": True
                    }
                })

        if not task_id:
            return jsonify({
                "success": False,
                "error": "Укажите task_id или simulation_id"
            }), 400

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)

        if not task:
            return jsonify({
                "success": False,
                "error": f"Задача не найдена: {task_id}"
            }), 404

        return jsonify({
            "success": True,
            "data": task.to_dict()
        })

    except Exception as e:
        logger.error(f"Ошибка запроса статуса задачи: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== Интерфейс получения отчётов ==============

@report_bp.route('/<report_id>', methods=['GET'])
def get_report(report_id: str):
    """
    Получение деталей отчёта

    Ответ:
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "simulation_id": "sim_xxxx",
                "status": "completed",
                "outline": {...},
                "markdown_content": "...",
                "created_at": "...",
                "completed_at": "..."
            }
        }
    """
    try:
        report = ReportManager.get_report(report_id)

        if not report:
            return jsonify({
                "success": False,
                "error": f"Отчёт не найден: {report_id}"
            }), 404

        return jsonify({
            "success": True,
            "data": report.to_dict()
        })

    except Exception as e:
        logger.error(f"Ошибка получения отчёта: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
def get_report_by_simulation(simulation_id: str):
    """
    Получение отчёта по ID моделирования

    Ответ:
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                ...
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)

        if not report:
            return jsonify({
                "success": False,
                "error": f"Для этого моделирования отчёт не найден: {simulation_id}",
                "has_report": False
            }), 404

        return jsonify({
            "success": True,
            "data": report.to_dict(),
            "has_report": True
        })

    except Exception as e:
        logger.error(f"Ошибка получения отчёта: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/list', methods=['GET'])
def list_reports():
    """
    Список всех отчётов

    Query-параметры:
        simulation_id: фильтрация по ID моделирования (необязательно)
        limit: ограничение количества возвращаемых записей (по умолчанию 50)

    Ответ:
        {
            "success": true,
            "data": [...],
            "count": 10
        }
    """
    try:
        simulation_id = request.args.get('simulation_id')
        limit = request.args.get('limit', 50, type=int)

        reports = ReportManager.list_reports(
            simulation_id=simulation_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": [r.to_dict() for r in reports],
            "count": len(reports)
        })

    except Exception as e:
        logger.error(f"Ошибка получения списка отчётов: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/download', methods=['GET'])
def download_report(report_id: str):
    """
    Скачивание отчёта (формат Markdown)

    Возвращает Markdown-файл
    """
    try:
        report = ReportManager.get_report(report_id)

        if not report:
            return jsonify({
                "success": False,
                "error": f"Отчёт не найден: {report_id}"
            }), 404

        md_path = ReportManager._get_report_markdown_path(report_id)

        if not os.path.exists(md_path):
            # Если MD-файл не найден, генерируем временный файл
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(report.markdown_content)
                temp_path = f.name

            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f"{report_id}.md"
            )

        return send_file(
            md_path,
            as_attachment=True,
            download_name=f"{report_id}.md"
        )

    except Exception as e:
        logger.error(f"Ошибка скачивания отчёта: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>', methods=['DELETE'])
def delete_report(report_id: str):
    """Удаление отчёта"""
    try:
        success = ReportManager.delete_report(report_id)

        if not success:
            return jsonify({
                "success": False,
                "error": f"Отчёт не найден: {report_id}"
            }), 404

        return jsonify({
            "success": True,
            "message": f"Отчёт удалён: {report_id}"
        })

    except Exception as e:
        logger.error(f"Ошибка удаления отчёта: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Интерфейс диалога с Report Agent ==============

@report_bp.route('/chat', methods=['POST'])
def chat_with_report_agent():
    """
    Диалог с Report Agent

    Report Agent может самостоятельно вызывать инструменты поиска для ответа на вопросы в процессе диалога

    Запрос (JSON):
        {
            "simulation_id": "sim_xxxx",        // обязательно, ID моделирования
            "message": "Объясните динамику общественного мнения",    // обязательно, сообщение пользователя
            "chat_history": [                   // необязательно, история диалога
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }

    Ответ:
        {
            "success": true,
            "data": {
                "response": "Ответ Agent...",
                "tool_calls": [список вызванных инструментов],
                "sources": [источники информации]
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        message = data.get('message')
        chat_history = data.get('chat_history', [])

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Укажите simulation_id"
            }), 400

        if not message:
            return jsonify({
                "success": False,
                "error": "Укажите message"
            }), 400

        # Получение информации о моделировании и проекте
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"Моделирование не найдено: {simulation_id}"
            }), 404

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Проект не найден: {state.project_id}"
            }), 404

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Нет ID графа"
            }), 400

        simulation_requirement = project.simulation_requirement or ""

        # Создание Agent и ведение диалога
        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement
        )

        result = agent.chat(message=message, chat_history=chat_history)

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        logger.error(f"Ошибка диалога: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Интерфейс прогресса и разделов отчёта ==============

@report_bp.route('/<report_id>/progress', methods=['GET'])
def get_report_progress(report_id: str):
    """
    Получение прогресса генерации отчёта (в реальном времени)

    Ответ:
        {
            "success": true,
            "data": {
                "status": "generating",
                "progress": 45,
                "message": "Генерация раздела: Ключевые выводы",
                "current_section": "Ключевые выводы",
                "completed_sections": ["Резюме", "Контекст моделирования"],
                "updated_at": "2025-12-09T..."
            }
        }
    """
    try:
        progress = ReportManager.get_progress(report_id)

        if not progress:
            return jsonify({
                "success": False,
                "error": f"Отчёт не найден или нет данных о прогрессе: {report_id}"
            }), 404

        return jsonify({
            "success": True,
            "data": progress
        })

    except Exception as e:
        logger.error(f"Ошибка получения прогресса отчёта: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/sections', methods=['GET'])
def get_report_sections(report_id: str):
    """
    Получение списка сгенерированных разделов (поразделный вывод)

    Фронтенд может опрашивать этот интерфейс для получения содержимого уже сгенерированных разделов,
    не дожидаясь завершения всего отчёта

    Ответ:
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "sections": [
                    {
                        "filename": "section_01.md",
                        "section_index": 1,
                        "content": "## Резюме\\n\\n..."
                    },
                    ...
                ],
                "total_sections": 3,
                "is_complete": false
            }
        }
    """
    try:
        sections = ReportManager.get_generated_sections(report_id)

        # Получение статуса отчёта
        report = ReportManager.get_report(report_id)
        is_complete = report is not None and report.status == ReportStatus.COMPLETED

        return jsonify({
            "success": True,
            "data": {
                "report_id": report_id,
                "sections": sections,
                "total_sections": len(sections),
                "is_complete": is_complete
            }
        })

    except Exception as e:
        logger.error(f"Ошибка получения списка разделов: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/section/<int:section_index>', methods=['GET'])
def get_single_section(report_id: str, section_index: int):
    """
    Получение содержимого одного раздела

    Ответ:
        {
            "success": true,
            "data": {
                "filename": "section_01.md",
                "content": "## Резюме\\n\\n..."
            }
        }
    """
    try:
        section_path = ReportManager._get_section_path(report_id, section_index)

        if not os.path.exists(section_path):
            return jsonify({
                "success": False,
                "error": f"Раздел не найден: section_{section_index:02d}.md"
            }), 404

        with open(section_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return jsonify({
            "success": True,
            "data": {
                "filename": f"section_{section_index:02d}.md",
                "section_index": section_index,
                "content": content
            }
        })

    except Exception as e:
        logger.error(f"Ошибка получения содержимого раздела: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Интерфейс проверки статуса отчёта ==============

@report_bp.route('/check/<simulation_id>', methods=['GET'])
def check_report_status(simulation_id: str):
    """
    Проверка наличия отчёта для моделирования и его статуса

    Используется фронтендом для определения, разблокирована ли функция Interview

    Ответ:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "has_report": true,
                "report_status": "completed",
                "report_id": "report_xxxx",
                "interview_unlocked": true
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)

        has_report = report is not None
        report_status = report.status.value if report else None
        report_id = report.report_id if report else None

        # Interview разблокируется только после завершения отчёта
        interview_unlocked = has_report and report.status == ReportStatus.COMPLETED

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "has_report": has_report,
                "report_status": report_status,
                "report_id": report_id,
                "interview_unlocked": interview_unlocked
            }
        })

    except Exception as e:
        logger.error(f"Ошибка проверки статуса отчёта: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Интерфейс логов Agent ==============

@report_bp.route('/<report_id>/agent-log', methods=['GET'])
def get_agent_log(report_id: str):
    """
    Получение подробного журнала выполнения Report Agent

    Получение в реальном времени каждого шага в процессе генерации отчёта, включая:
    - Начало отчёта, начало/завершение планирования
    - Начало каждого раздела, вызовы инструментов, ответы LLM, завершение
    - Завершение или ошибка отчёта

    Query-параметры:
        from_line: с какой строки начинать чтение (необязательно, по умолчанию 0, для инкрементального получения)

    Ответ:
        {
            "success": true,
            "data": {
                "logs": [
                    {
                        "timestamp": "2025-12-13T...",
                        "elapsed_seconds": 12.5,
                        "report_id": "report_xxxx",
                        "action": "tool_call",
                        "stage": "generating",
                        "section_title": "Резюме",
                        "section_index": 1,
                        "details": {
                            "tool_name": "insight_forge",
                            "parameters": {...},
                            ...
                        }
                    },
                    ...
                ],
                "total_lines": 25,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)

        log_data = ReportManager.get_agent_log(report_id, from_line=from_line)

        return jsonify({
            "success": True,
            "data": log_data
        })

    except Exception as e:
        logger.error(f"Ошибка получения логов Agent: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/agent-log/stream', methods=['GET'])
def stream_agent_log(report_id: str):
    """
    Получение полного журнала Agent (все записи за один запрос)

    Ответ:
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 25
            }
        }
    """
    try:
        logs = ReportManager.get_agent_log_stream(report_id)

        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })

    except Exception as e:
        logger.error(f"Ошибка получения логов Agent: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Интерфейс консольных логов ==============

@report_bp.route('/<report_id>/console-log', methods=['GET'])
def get_console_log(report_id: str):
    """
    Получение журнала консольного вывода Report Agent

    Получение в реальном времени консольного вывода (INFO, WARNING и т.д.) в процессе генерации отчёта.
    В отличие от интерфейса agent-log, возвращающего структурированные JSON-логи,
    здесь возвращаются логи в текстовом формате консольного стиля.

    Query-параметры:
        from_line: с какой строки начинать чтение (необязательно, по умолчанию 0, для инкрементального получения)

    Ответ:
        {
            "success": true,
            "data": {
                "logs": [
                    "[19:46:14] INFO: Поиск завершён: найдено 15 релевантных фактов",
                    "[19:46:14] INFO: Поиск по графу: graph_id=xxx, query=...",
                    ...
                ],
                "total_lines": 100,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)

        log_data = ReportManager.get_console_log(report_id, from_line=from_line)

        return jsonify({
            "success": True,
            "data": log_data
        })

    except Exception as e:
        logger.error(f"Ошибка получения консольных логов: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/console-log/stream', methods=['GET'])
def stream_console_log(report_id: str):
    """
    Получение полного консольного журнала (все записи за один запрос)

    Ответ:
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 100
            }
        }
    """
    try:
        logs = ReportManager.get_console_log_stream(report_id)

        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })

    except Exception as e:
        logger.error(f"Ошибка получения консольных логов: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Интерфейс вызова инструментов (для отладки) ==============

@report_bp.route('/tools/search', methods=['POST'])
def search_graph_tool():
    """
    Интерфейс инструмента поиска по графу (для отладки)

    Запрос (JSON):
        {
            "graph_id": "mirofish_xxxx",
            "query": "поисковый запрос",
            "limit": 10
        }
    """
    try:
        data = request.get_json() or {}

        graph_id = data.get('graph_id')
        query = data.get('query')
        limit = data.get('limit', 10)

        if not graph_id or not query:
            return jsonify({
                "success": False,
                "error": "Укажите graph_id и query"
            }), 400

        from ..services.zep_tools import ZepToolsService

        tools = ZepToolsService()
        result = tools.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": result.to_dict()
        })

    except Exception as e:
        logger.error(f"Ошибка поиска по графу: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/tools/statistics', methods=['POST'])
def get_graph_statistics_tool():
    """
    Интерфейс инструмента статистики графа (для отладки)

    Запрос (JSON):
        {
            "graph_id": "mirofish_xxxx"
        }
    """
    try:
        data = request.get_json() or {}

        graph_id = data.get('graph_id')

        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Укажите graph_id"
            }), 400

        from ..services.zep_tools import ZepToolsService

        tools = ZepToolsService()
        result = tools.get_graph_statistics(graph_id)

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        logger.error(f"Ошибка получения статистики графа: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
