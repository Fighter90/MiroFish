<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="Логотип MiroFish" width="75%"/>

Система мультиагентного моделирования общественного мнения — **v1.1.0**
</br>
<em>Multi-Agent Social Opinion Simulation System</em>

[![GitHub Stars](https://img.shields.io/github/stars/Fighter90/MiroFish?style=flat-square&color=DAA520)](https://github.com/Fighter90/MiroFish/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/Fighter90/MiroFish?style=flat-square)](https://github.com/Fighter90/MiroFish/network)
[![Docker](https://img.shields.io/badge/Docker-Build-2496ED?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/)

[English](./README-EN.md) | [Русский](./README.md)

</div>

## Обзор

**MiroFish** — система прогнозного моделирования, основанная на технологиях GraphRAG и мультиагентной симуляции. Из исходных документов (аналитические отчёты, новостные материалы, описания ситуаций) система автоматически строит граф знаний, извлекая сущности, факты и причинно-следственные связи. На основе графа генерируется популяция автономных AI-агентов с индивидуальными когнитивными профилями, долговременной памятью (ZEP) и социальными связями.

Агенты взаимодействуют в симулированной социальной среде: публикуют посты, комментируют, голосуют и формируют кластеры мнений. Система фиксирует динамику распространения информации, выявляет лидеров влияния и прогнозирует реакцию аудитории до наступления реального события.

> **Вход:** загрузите документы и опишите сценарий моделирования на естественном языке.
> **Выход:** структурированный аналитический отчёт и интерактивная среда для верификации результатов.

## Архитектура

### Рабочий процесс

1. **Построение графа знаний (GraphRAG)** — NLP-анализ документов: извлечение именованных сущностей, фактов и причинно-следственных связей
2. **Генерация популяции агентов** — создание AI-агентов с когнитивными профилями, памятью (ZEP) и социальным графом
3. **Мультиплатформенная симуляция** — параллельное моделирование на двух социальных платформах: публикации, комментарии, голосования, подписки
4. **Аналитический отчёт (ReportAgent)** — автоматическое выявление трендов, кластеров мнений, лидеров влияния и точек бифуркации
5. **Верификация результатов** — интервью с агентами, пакетные опросы, анализ мотивации

### Технологический стек

| Компонент | Технология |
|-----------|------------|
| Фронтенд | Vue.js 3 (Composition API), Vite |
| Бэкенд | Python 3.11+, Flask |
| Граф знаний | GraphRAG |
| Память агентов | ZEP Cloud |
| Симуляция | OASIS (Open Agent Social Interaction Simulations) |
| LLM | Любой OpenAI-совместимый API (Qwen, GPT-4, Claude, Mistral) |
| Контейнеризация | Docker, Docker Compose |

## Скриншоты

<div align="center">
<table>
<tr>
<td><img src="./static/image/Screenshot/screenshot_1.png" alt="Скриншот 1" width="100%"/></td>
<td><img src="./static/image/Screenshot/screenshot_2.png" alt="Скриншот 2" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/screenshot_3.png" alt="Скриншот 3" width="100%"/></td>
<td><img src="./static/image/Screenshot/screenshot_4.png" alt="Скриншот 4" width="100%"/></td>
</tr>
</table>
</div>

## Быстрый старт

### Вариант 1: Из исходного кода (рекомендуется)

#### Предварительные требования

| Инструмент | Версия | Проверка |
|------------|--------|----------|
| **Node.js** | 18+ | `node -v` |
| **Python** | 3.11–3.12 | `python --version` |
| **uv** | Последняя | `uv --version` |

#### 1. Настройка переменных окружения

```bash
cp .env.example .env
```

**Обязательные переменные:**

```env
# LLM API (OpenAI-совместимый формат)
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# ZEP Cloud — сервис памяти агентов
# Бесплатный тариф: https://app.getzep.com/
ZEP_API_KEY=your_zep_api_key
```

#### 2. Установка зависимостей

```bash
# Все зависимости одной командой
npm run setup:all
```

Или пошагово:

```bash
npm run setup           # Node-зависимости (корень + фронтенд)
npm run setup:backend   # Python-зависимости (бэкенд)
```

#### 3. Запуск

```bash
npm run dev
```

- Фронтенд: `http://localhost:3000`
- API бэкенда: `http://localhost:5001`

### Вариант 2: Docker

```bash
cp .env.example .env
docker compose up -d
```

## Стоимость

Средняя стоимость одной симуляции — около $5 на API-вызовах. Для начала рекомендуется ограничить количество раундов до 20–40.

## Changelog

Полная история изменений — в файле [CHANGELOG.md](./CHANGELOG.md).

## Благодарности

Движок симуляции работает на базе **[OASIS (Open Agent Social Interaction Simulations)](https://github.com/camel-ai/oasis)**. Благодарим команду CAMEL-AI за вклад в открытый код.
