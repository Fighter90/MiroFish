FROM python:3.11

# Установка Node.js (версия >=18) и необходимых инструментов
RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm \
  && rm -rf /var/lib/apt/lists/*

# Копирование uv из официального образа
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# Сначала копируем файлы описания зависимостей для использования кэша
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/package-lock.json ./frontend/
COPY backend/pyproject.toml backend/uv.lock ./backend/

# Установка зависимостей (Node + Python)
RUN npm ci \
  && npm ci --prefix frontend \
  && cd backend && uv sync --frozen

# Копирование исходного кода проекта
COPY . .

# Очистка Vite-кеша для гарантии актуальности фронтенда
RUN rm -rf /app/node_modules/.vite /app/frontend/node_modules/.vite

# Диагностика: проверить что файлы скопированы корректно
RUN echo "=== BUILD DIAGNOSTIC ===" \
  && grep -o 'MIROFISH\|АГЕНТНОЕ МОДЕЛИРОВАНИЕ' /app/frontend/src/views/Home.vue || true \
  && ls -la /app/frontend/src/assets/logo/dashboard-hero.svg 2>/dev/null || echo "dashboard-hero.svg NOT FOUND" \
  && echo "=== END DIAGNOSTIC ==="

EXPOSE 3000 5001

# Одновременный запуск фронтенда и бэкенда (режим разработки)
CMD ["npm", "run", "dev"]
