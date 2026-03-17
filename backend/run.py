"""
MiroFish Backend — точка входа
"""

import os
import sys

# Решение проблемы кодировки в консоли Windows: установка UTF-8 до всех импортов
if sys.platform == 'win32':
    # Установка переменной окружения для использования UTF-8 в Python
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    # Перенастройка стандартных потоков вывода на UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Добавление корневой директории проекта в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def main():
    """Главная функция"""
    # Проверка конфигурации
    errors = Config.validate()
    if errors:
        print("Ошибки конфигурации:")
        for err in errors:
            print(f"  - {err}")
        print("\nПроверьте настройки в файле .env")
        sys.exit(1)

    # Создание приложения
    app = create_app()

    # Получение параметров запуска
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG

    # Запуск сервера
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    main()
