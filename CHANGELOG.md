# Changelog

Все значимые изменения проекта документируются в этом файле.

## [1.3.2] — 2026-04-24

### Исправления

- **Белый экран на `/simulation/:id`**: компоненты `Step2EnvSetup.vue` и `Step3Simulation.vue` вызывали `useI18n()` без импорта `useI18n from 'vue-i18n'` (`-X ours` merge потерял импорт). Добавлен в оба файла.
- **`/api/graph/ontology/generate` падал с `NameError: name 'system_prompt' is not defined`**. `-X ours` merge оставил вызов без инициализации `system_prompt` (upstream собирал его из `ONTOLOGY_SYSTEM_PROMPT` + `get_language_instruction()`). Собираю явно.
- **`ontology_generator._validate_and_process`**: добавлен отсутствующий `entity_name_map: Dict[str, str] = {}` — без него валидация edge_types падала.
- **3 фоновых потока без захвата локали**: `simulation_runner._monitor_simulation`, `graph_builder._build_graph_worker`, `zep_graph_memory_updater._worker_loop` — добавлен захват `get_locale()` перед `threading.Thread(...)` + параметр в сигнатуре + `set_locale(locale)` внутри метода.

### Надёжность

- **Volume `uploads/` вынесен вне репо.** На проде `deploy.yml` делал `rm -rf MiroFish` при каждом пуше, а volume docker-compose монтировал из `./backend/uploads` — каждая симуляция с state.json, профилями и логами стиралась на следующем деплое. Теперь `docker-compose.yml` использует `${UPLOADS_VOLUME:-./backend/uploads}`, а `deploy.yml` экспортирует `UPLOADS_VOLUME=/var/lib/mirofish/uploads`.

### Безопасность

- `backend/app/config.py`: убран fallback `SECRET_KEY='mirofish-secret-key'`; `Config.validate()` теперь жёстко требует `SECRET_KEY`. Дефолт `FLASK_DEBUG` изменён с `True` на `False`.
- `backend/app/__init__.py`: `CORS(origins="*")` сужен до списка из env `CORS_ORIGINS` (дефолт `https://mirprognoz.ru,http://localhost:3000`).

## [1.3.1] — 2026-04-24

### Исправления

- **nginx**: сужен блок `return 404` — оставлены только `/.env` и `/.git`. Vite dev-пути (`/@vite/*`, `/src/*`, `/node_modules/*`) возвращали 404 даже авторизованным пользователям, сайт не работал.
- **Post-merge регрессия из upstream**: в API-хендлерах графа / отчёта / симуляции фоновый поток вызывал `set_locale(current_locale)` без захвата `current_locale` в request-context — гарантированный `NameError` при запуске задачи. Локаль теперь захватывается явно.
- **Утечка информации в 500-ответах**: убран `"traceback": traceback.format_exc()` из 49 `jsonify` 500-ответов в `backend/app/api/{graph,report,simulation}.py`. Логируется по-прежнему, но клиенту не отдаётся.
- **Дефолт локали**: `backend/app/utils/locale.py` `'zh'` → `'ru'`. Форк русскоязычный; без правки LLM получал китайскую инструкцию и фоновые потоки генерировали китайские ответы.
- **Security workflow Trivy**: упал с `no space left on device` на runner'е. Добавлен `jlumbroso/free-disk-space` и отключён секрет-сканер Trivy (дубль с TruffleHog).

## [1.3.0] — 2026-04-24

### Безопасность
- **Порты Docker забинжены на 127.0.0.1** — Vite (`3000`) и Flask (`5001`) больше не слушают на `0.0.0.0`. Доступ только через nginx-reverse-proxy. Закрывает CVE-2025-30208 / 31125 / 31486 / 32395 (Vite dev-server) и CVE-2024-23331 (Vite `server.fs.deny` bypass).
- **`SECRET_KEY` и `FLASK_DEBUG=false` через GitHub Secrets** — деплой-скрипт теперь требует секрет `FLASK_SECRET_KEY` и пишет его в `.env` на сервере. Ранее Flask использовал дефолтный `mirofish-secret-key` из `backend/app/config.py` (подписи сессий поддавались подделке) и оставался с `DEBUG=true` (потенциальный werkzeug-debugger RCE).
- **`chmod 600 .env`** после генерации на сервере.
- Обновление фронтенд-зависимостей из upstream: `axios 1.14.0`, `rollup`, `picomatch` — закрывает 3 high-severity npm-уязвимости.

### Инфраструктура (на сервере, не в репозитории)
- nginx Basic Auth перед всем сайтом, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
- UFW: allow 22/80/443, deny 3000/5001/10050.
- SSH: `PasswordAuthentication no`, `PermitRootLogin prohibit-password`.
- Zabbix-agent выключен.

### Синхронизация с upstream `666ghj/MiroFish`
- `vue-i18n` обновлён с v9 до v11.
- Добавлена i18n-инфраструктура: `backend/app/utils/locale.py` (thread-local, Accept-Language), `frontend/src/i18n/index.js`, `locales/{en,zh,languages}.json`, `LanguageSwitcher.vue`.
- Граф: принудительный PascalCase для имён сущностей и SCREAMING_SNAKE_CASE для рёбер на уровне валидации онтологии.
- Конфликты резолвлены стратегией `ours`: русский UI форка сохранён, инфраструктура i18n подтянута как follow-up-ready инструментарий.

### Документация
- Удалены `README-EN.md` и `README-ZH.md` — проект поддерживается только на русском.

## [1.2.0] — 2026-03-19

### Улучшения моделей и NLP
- Обновление LLM-моделей: Qwen 2.5 (72B/7B) → Qwen 3.5 (122B/27B) — значительное повышение качества генерации
- Автоматическая нормализация имён сущностей — приведение к именительному падежу через LLM
- Нормализация перенесена в `zep_entity_reader.py` — покрывает все точки вызова (граф, превью, профили)
- Инструкции в промпте онтологии: запрет стран как агентов, обязательный именительный падеж

### Интерфейс
- Ссылки на скачивание тестовых примеров (документ + промпт) на главной странице
- Анимации и hover-эффекты на главной: fadeInUp, heroFloat, gradientShift, tagShine
- Исправлены цвета nav-link при наведении/активности (чёрный вместо белого)
- Добавлена ссылка «Главная» на странице помощи

### Документация
- README дополнен: подробные требования к документам и промптам, описание платформ симуляции
- Секция «Тестовые примеры» с инструкцией по использованию
- CHANGELOG обновлён

### Инфраструктура
- Деплой через tarball вместо git fetch — обход проблем с credentials
- Создание .env из GitHub secrets при каждом деплое
- Исправлен axios baseURL — запросы через Vite proxy вместо localhost

## [1.1.0] — 2026-03-19

### Изменения интерфейса
- Бренд «MIROFISH» заменён на «АГЕНТНОЕ МОДЕЛИРОВАНИЕ» на всех страницах
- Логотип заменён на аналитический дашборд (dashboard-hero.svg)
- Ссылка «Помощь» — чёрный текст на белом фоне (#000000)
- Все тексты главной страницы и документации переписаны в научном стиле
- Убраны абстракции: «зёрна реальности», «движок коллективного интеллекта», «виртуальный мир», «позиция Бога»
- Убраны конкретные названия платформ (Twitter/Reddit) — заменены на обобщённые формулировки
- Полная русификация оставшихся английских строк в компонентах симуляции

### Инфраструктура
- Настроен CI-пайплайн: Ruff lint, Pyright type-check, pytest, frontend build
- Настроен Security-пайплайн: TruffleHog, Bandit SAST, pip-audit, npm audit, Trivy
- Настроен автоматический деплой на VPS через SSH (appleboy/ssh-action)
- Настроен автоматический Release при создании тегов
- Исправлена проблема с Docker-кешем при деплое (--no-cache, system prune)
- Очистка Vite-кеша при каждом запуске dev-сервера

### Документация
- README переписан в научном стиле с таблицей технологического стека
- HelpView (страница «Помощь») полностью переработана — научная терминология

## [1.0.0] — 2026-03-19

### Первый релиз русского форка
- Полная русификация интерфейса и документации
- Перевод всех китайских текстов на русский язык
- Исправление ошибки 500 от тегов `<think>` в reasoning-моделях
