"""
MiroFish Backend — фабрика Flask-приложения
"""

import os
import warnings

# Подавление предупреждений multiprocessing resource_tracker (от сторонних библиотек, например transformers)
# Необходимо установить до всех остальных импортов
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Фабричная функция Flask-приложения"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Настройка кодировки JSON: прямое отображение Unicode (вместо формата \uXXXX)
    # Flask >= 2.3 использует app.json.ensure_ascii, старые версии — конфиг JSON_AS_ASCII
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    # Настройка логирования
    logger = setup_logger('mirofish')

    # Вывод информации о запуске только в дочернем процессе reloader (чтобы не дублировать в debug-режиме)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend запускается...")
        logger.info("=" * 50)

    # Включение CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Регистрация функции очистки процессов симуляции (завершение всех процессов при остановке сервера)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Зарегистрирована функция очистки процессов симуляции")

    # Middleware логирования запросов
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Запрос: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Тело запроса: {request.get_json(silent=True)}")

    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"Ответ: {response.status_code}")
        return response

    # Регистрация блюпринтов
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')

    # Проверка состояния
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}

    if should_log_startup:
        logger.info("MiroFish Backend успешно запущен")

    return app
