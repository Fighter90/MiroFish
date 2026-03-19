<template>
  <div class="help-container">
    <nav class="navbar">
      <router-link to="/" class="nav-brand">АГЕНТНОЕ МОДЕЛИРОВАНИЕ</router-link>
      <div class="nav-links">
        <router-link to="/help" class="nav-link active">Помощь</router-link>
        <a href="https://github.com/Fighter90/MiroFish" target="_blank" class="github-link">
          GitHub <span class="arrow">↗</span>
        </a>
      </div>
    </nav>

    <div class="help-content">
      <div class="help-hero">
        <div class="help-tag">Документация</div>
        <h1 class="help-title">Руководство пользователя</h1>
        <p class="help-subtitle">Техническое руководство по работе с системой</p>
      </div>

      <!-- Навигация по разделам -->
      <div class="help-nav">
        <a v-for="section in sections" :key="section.id" :href="'#' + section.id" class="help-nav-item" :class="{ active: activeSection === section.id }" @click.prevent="scrollToSection(section.id)">
          <span class="nav-num">{{ section.num }}</span>
          {{ section.title }}
        </a>
      </div>

      <!-- Что такое MiroFish -->
      <section id="about" class="help-section">
        <div class="section-header">
          <span class="section-num">01</span>
          <h2>Что такое MiroFish?</h2>
        </div>
        <div class="section-body">
          <p>
            <strong>MiroFish</strong> — система мультиагентного моделирования общественного мнения. На основе загруженных документов строится граф знаний (GraphRAG), из которого генерируются автономные AI-агенты с индивидуальными когнитивными профилями, долговременной памятью (ZEP) и социальными связями. Агенты взаимодействуют в симулированной социальной среде, что позволяет прогнозировать реакцию аудитории на заданные сценарии.
          </p>
          <div class="feature-grid">
            <div class="feature-card">
              <div class="feature-icon">◈</div>
              <div class="feature-title">Прогнозирование</div>
              <div class="feature-desc">Количественное моделирование общественной реакции на события, решения и информационные поводы</div>
            </div>
            <div class="feature-card">
              <div class="feature-icon">◇</div>
              <div class="feature-title">Граф знаний</div>
              <div class="feature-desc">Автоматическое извлечение сущностей и причинно-следственных связей из документов методами NLP</div>
            </div>
            <div class="feature-card">
              <div class="feature-icon">▣</div>
              <div class="feature-title">Мультиплатформенность</div>
              <div class="feature-desc">Параллельная симуляция на нескольких социальных платформах для охвата различных коммуникативных моделей</div>
            </div>
            <div class="feature-card">
              <div class="feature-icon">⬡</div>
              <div class="feature-title">Глубокий анализ</div>
              <div class="feature-desc">Структурированный аналитический отчёт (ReportAgent) и верификация результатов через интервью с агентами</div>
            </div>
          </div>
        </div>
      </section>

      <!-- Быстрый старт -->
      <section id="quickstart" class="help-section">
        <div class="section-header">
          <span class="section-num">02</span>
          <h2>Быстрый старт</h2>
        </div>
        <div class="section-body">
          <p>Чтобы запустить первую симуляцию, выполните три простых действия на главной странице:</p>

          <div class="step-block">
            <div class="step-marker">A</div>
            <div class="step-content">
              <h3>Загрузите документы</h3>
              <p>Перетащите файлы в зону загрузки или нажмите на неё для выбора. Система принимает форматы <code>PDF</code>, <code>MD</code> и <code>TXT</code>. Документы дают контекст — чем подробнее материал, тем реалистичнее симуляция.</p>
              <div class="tip-box">
                <span class="tip-label">Совет</span>
                Подойдут новостные статьи, аналитические отчёты, описания ситуаций, пресс-релизы — любой текст, описывающий контекст события.
              </div>
            </div>
          </div>

          <div class="step-block">
            <div class="step-marker">B</div>
            <div class="step-content">
              <h3>Напишите промпт — задачу для моделирования</h3>
              <p>В текстовом поле опишите сценарий, который хотите исследовать. Формулируйте как вопрос или гипотезу.</p>
              <div class="examples-box">
                <div class="examples-title">Примеры промптов:</div>
                <ul>
                  <li>«Как отреагирует общество, если Авито закроется?»</li>
                  <li>«Что будет, если ввести четырёхдневную рабочую неделю в России?»</li>
                  <li>«Как воспримут запрет на продажу энергетиков несовершеннолетним?»</li>
                  <li>«Реакция на объявление о переходе на электронные паспорта»</li>
                </ul>
              </div>
            </div>
          </div>

          <div class="step-block">
            <div class="step-marker">C</div>
            <div class="step-content">
              <h3>Нажмите «Запустить симуляцию»</h3>
              <p>Кнопка станет активной после загрузки хотя бы одного файла и заполнения промпта. После нажатия система автоматически перейдёт к построению графа знаний.</p>
            </div>
          </div>
        </div>
      </section>

      <!-- Рабочий процесс -->
      <section id="workflow" class="help-section">
        <div class="section-header">
          <span class="section-num">03</span>
          <h2>Рабочий процесс: 5 шагов</h2>
        </div>
        <div class="section-body">

          <div class="workflow-card">
            <div class="wf-header">
              <span class="wf-num">Шаг 1</span>
              <span class="wf-title">Построение графа знаний</span>
              <span class="wf-time">~2-5 мин</span>
            </div>
            <div class="wf-body">
              <p>Система анализирует загруженные документы и автоматически:</p>
              <ul>
                <li>Извлекает ключевые сущности (людей, организации, события, места)</li>
                <li>Определяет связи между ними</li>
                <li>Строит интерактивный граф (GraphRAG), который визуализируется в левой панели</li>
              </ul>
              <p>Вы можете переключаться между режимами отображения: <strong>Граф</strong>, <strong>Две колонки</strong>, <strong>Рабочий стол</strong>.</p>
            </div>
          </div>

          <div class="workflow-card">
            <div class="wf-header">
              <span class="wf-num">Шаг 2</span>
              <span class="wf-title">Настройка среды симуляции</span>
              <span class="wf-time">~3-10 мин</span>
            </div>
            <div class="wf-body">
              <p>На основе графа знаний система генерирует популяцию AI-агентов с индивидуальными характеристиками:</p>
              <ul>
                <li><strong>Когнитивный профиль</strong> — демография, профессия, ценности, поведенческие установки</li>
                <li><strong>Долговременная память (ZEP)</strong> — контекстные знания, извлечённые из документов</li>
                <li><strong>Социальный граф</strong> — связи и отношения между агентами</li>
              </ul>
              <p>Здесь можно просмотреть профили сгенерированных агентов и настроить параметры платформ.</p>
            </div>
          </div>

          <div class="workflow-card">
            <div class="wf-header">
              <span class="wf-num">Шаг 3</span>
              <span class="wf-title">Запуск симуляции</span>
              <span class="wf-time">~5-30 мин</span>
            </div>
            <div class="wf-body">
              <p>Агенты взаимодействуют на двух симулированных социальных платформах одновременно:</p>
              <ul>
                <li><strong>Платформа коротких сообщений</strong> — публикации, репосты, лайки, комментарии</li>
                <li><strong>Платформа дискуссий</strong> — развёрнутые обсуждения, треды, голосования</li>
              </ul>
              <p>В реальном времени отображаются: количество действий, новые посты, динамика графа. Граф обновляется каждые 30 секунд.</p>
            </div>
          </div>

          <div class="workflow-card">
            <div class="wf-header">
              <span class="wf-num">Шаг 4</span>
              <span class="wf-title">Генерация отчёта</span>
              <span class="wf-time">~3-8 мин</span>
            </div>
            <div class="wf-body">
              <p>Специальный ReportAgent анализирует все результаты симуляции:</p>
              <ul>
                <li>Выявляет ключевые тренды и настроения</li>
                <li>Определяет группы мнений и лидеров влияния</li>
                <li>Формирует структурированный аналитический отчёт</li>
              </ul>
              <p>Процесс генерации отображается в логах агента и системной консоли.</p>
            </div>
          </div>

          <div class="workflow-card">
            <div class="wf-header">
              <span class="wf-num">Шаг 5</span>
              <span class="wf-title">Углублённое взаимодействие</span>
              <span class="wf-time">без ограничений</span>
            </div>
            <div class="wf-body">
              <p>После завершения симуляции доступны инструменты верификации и углублённого анализа:</p>
              <ul>
                <li><strong>Чат с отчётом</strong> — задавайте уточняющие вопросы по результатам</li>
                <li><strong>Интервью с агентами</strong> — диалог с участниками симуляции для верификации мотивации и позиции</li>
                <li><strong>Пакетные интервью</strong> — опрашивайте группы агентов одновременно</li>
              </ul>
            </div>
          </div>

        </div>
      </section>

      <!-- Форматы файлов -->
      <section id="formats" class="help-section">
        <div class="section-header">
          <span class="section-num">04</span>
          <h2>Поддерживаемые форматы</h2>
        </div>
        <div class="section-body">
          <div class="format-table">
            <div class="format-row header">
              <span>Формат</span>
              <span>Описание</span>
              <span>Рекомендации</span>
            </div>
            <div class="format-row">
              <span class="format-ext">PDF</span>
              <span>Документы, отчёты, статьи</span>
              <span>Убедитесь, что текст в PDF не является сканом (изображением)</span>
            </div>
            <div class="format-row">
              <span class="format-ext">MD</span>
              <span>Markdown-файлы</span>
              <span>Идеально для структурированных описаний и заметок</span>
            </div>
            <div class="format-row">
              <span class="format-ext">TXT</span>
              <span>Текстовые файлы</span>
              <span>Простой текст без форматирования, кодировка UTF-8</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Советы -->
      <section id="tips" class="help-section">
        <div class="section-header">
          <span class="section-num">05</span>
          <h2>Советы и лучшие практики</h2>
        </div>
        <div class="section-body">
          <div class="tips-grid">
            <div class="tip-card">
              <div class="tip-num">01</div>
              <h3>Качество входных данных</h3>
              <p>Чем более детальный и контекстный документ вы загрузите, тем реалистичнее будет симуляция. Один подробный отчёт лучше десяти коротких заметок.</p>
            </div>
            <div class="tip-card">
              <div class="tip-num">02</div>
              <h3>Формулировка промпта</h3>
              <p>Задавайте конкретные вопросы. «Как отреагируют жители Москвы на закрытие метро на выходные?» лучше, чем «Что думают люди о метро?»</p>
            </div>
            <div class="tip-card">
              <div class="tip-num">03</div>
              <h3>Количество раундов</h3>
              <p>Для первого знакомства рекомендуем до 40 раундов симуляции. Это позволит получить результат за приемлемое время и расход API.</p>
            </div>
            <div class="tip-card">
              <div class="tip-num">04</div>
              <h3>Стоимость</h3>
              <p>Средняя стоимость одной симуляции — около $5 на API-вызовах. Начните с небольших экспериментов, чтобы оценить расходы.</p>
            </div>
            <div class="tip-card">
              <div class="tip-num">05</div>
              <h3>Интерпретация результатов</h3>
              <p>Используйте шаг 5 (Взаимодействие) для проверки гипотез. Спросите агентов напрямую, почему они так отреагировали.</p>
            </div>
            <div class="tip-card">
              <div class="tip-num">06</div>
              <h3>История проектов</h3>
              <p>Все запущенные симуляции сохраняются в базе на главной странице. Вы можете вернуться к любой из них в любое время.</p>
            </div>
          </div>
        </div>
      </section>

      <!-- FAQ -->
      <section id="faq" class="help-section">
        <div class="section-header">
          <span class="section-num">06</span>
          <h2>Частые вопросы</h2>
        </div>
        <div class="section-body">
          <div class="faq-list">
            <div class="faq-item" v-for="(faq, i) in faqs" :key="i">
              <div class="faq-question" @click="toggleFaq(i)">
                <span>{{ faq.q }}</span>
                <span class="faq-toggle">{{ openFaq === i ? '−' : '+' }}</span>
              </div>
              <div class="faq-answer" v-show="openFaq === i">
                {{ faq.a }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Футер -->
      <div class="help-footer">
        <div class="footer-line"></div>
        <p>MiroFish v1.1.0 — Мультиагентное моделирование общественного мнения</p>
        <router-link to="/" class="back-home">← Вернуться на главную</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const activeSection = ref('about')
const openFaq = ref(null)

const sections = [
  { id: 'about', num: '01', title: 'О системе' },
  { id: 'quickstart', num: '02', title: 'Быстрый старт' },
  { id: 'workflow', num: '03', title: 'Рабочий процесс' },
  { id: 'formats', num: '04', title: 'Форматы файлов' },
  { id: 'tips', num: '05', title: 'Советы' },
  { id: 'faq', num: '06', title: 'FAQ' },
]

const faqs = [
  { q: 'Какие LLM поддерживаются?', a: 'Система совместима с любым LLM через OpenAI-совместимый API. Рекомендуемые модели: Qwen, GPT-4, Claude, Mistral. Конфигурация задаётся через переменные окружения LLM_API_KEY, LLM_BASE_URL и LLM_MODEL_NAME.' },
  { q: 'Сколько стоит одна симуляция?', a: 'В среднем около $5, в зависимости от количества агентов, раундов и выбранной модели. Для тестирования рекомендуем ограничить число раундов до 20-40.' },
  { q: 'Что такое ZEP и зачем он нужен?', a: 'ZEP — сервис долговременной памяти для AI-агентов. Обеспечивает сохранение контекста между раундами симуляции, повышая когерентность поведения агентов. Бесплатного тарифа на getzep.com достаточно для базового использования.' },
  { q: 'Можно ли остановить симуляцию досрочно?', a: 'Да, на шаге 3 (Симуляция) доступна кнопка остановки. Уже накопленные данные будут использованы для генерации отчёта.' },
  { q: 'Почему две платформы?', a: 'Платформы моделируют различные коммуникативные паттерны: одна — короткие реакции и вирусное распространение, другая — развёрнутые дискуссии и аргументированные позиции. Комбинация обеспечивает более полный охват общественного мнения.' },
  { q: 'Как долго хранятся результаты?', a: 'Все результаты сохраняются на сервере и доступны через раздел «История» на главной странице. Вы можете вернуться к любой прошлой симуляции.' },
  { q: 'Что делать, если симуляция зависла?', a: 'Проверьте логи в консоли (шаг 3-4). Чаще всего причина — таймаут API. Попробуйте перезапустить симуляцию с меньшим количеством раундов или проверьте баланс на сервисе LLM.' },
]

const toggleFaq = (index) => {
  openFaq.value = openFaq.value === index ? null : index
}

const scrollToSection = (id) => {
  const el = document.getElementById(id)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const handleScroll = () => {
  const sectionEls = sections.map(s => document.getElementById(s.id)).filter(Boolean)
  for (let i = sectionEls.length - 1; i >= 0; i--) {
    if (sectionEls[i].getBoundingClientRect().top < 200) {
      activeSection.value = sections[i].id
      break
    }
  }
}

onMounted(() => window.addEventListener('scroll', handleScroll))
onUnmounted(() => window.removeEventListener('scroll', handleScroll))
</script>

<style scoped>
:root {
  --black: #000000;
  --white: #FFFFFF;
  --orange: #FF4500;
  --gray-light: #F5F5F5;
  --gray-text: #666666;
  --border: #E5E5E5;
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.help-container {
  min-height: 100vh;
  background: var(--white);
  font-family: var(--font-sans);
  color: var(--black);
}

/* Navbar */
.navbar {
  height: 60px;
  background: var(--black);
  color: var(--white);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 40px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-brand {
  font-family: var(--font-mono);
  font-weight: 800;
  letter-spacing: 1px;
  font-size: 1.2rem;
  color: var(--white);
  text-decoration: none;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 30px;
}

.nav-link {
  color: #000000;
  background: #FFFFFF;
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  font-weight: 600;
  padding: 4px 12px;
  border: none;
  transition: all 0.2s;
}

.nav-link:hover, .nav-link.active {
  background: var(--orange);
  color: #FFFFFF;
}

.github-link {
  color: var(--white);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  font-weight: 500;
  opacity: 0.8;
  transition: opacity 0.2s;
}

.github-link:hover { opacity: 1; }

.arrow { font-family: sans-serif; }

/* Content */
.help-content {
  max-width: 1000px;
  margin: 0 auto;
  padding: 60px 40px 100px;
}

/* Hero */
.help-hero {
  margin-bottom: 50px;
}

.help-tag {
  display: inline-block;
  background: var(--orange);
  color: var(--white);
  padding: 4px 10px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.75rem;
  letter-spacing: 1px;
  margin-bottom: 20px;
}

.help-title {
  font-size: 3.5rem;
  font-weight: 500;
  margin: 0 0 15px 0;
  letter-spacing: -1px;
}

.help-subtitle {
  font-size: 1.1rem;
  color: var(--gray-text);
}

/* Section nav */
.help-nav {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  margin-bottom: 60px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 20px;
}

.help-nav-item {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
  text-decoration: none;
  padding: 6px 14px;
  border: 1px solid transparent;
  transition: all 0.2s;
}

.help-nav-item:hover {
  color: var(--black);
  border-color: var(--border);
}

.help-nav-item.active {
  color: var(--black);
  border-color: var(--black);
}

.nav-num {
  opacity: 0.4;
  margin-right: 6px;
}

/* Sections */
.help-section {
  margin-bottom: 70px;
}

.section-header {
  display: flex;
  align-items: baseline;
  gap: 20px;
  margin-bottom: 30px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--border);
}

.section-num {
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--orange);
  font-size: 0.9rem;
}

.section-header h2 {
  font-size: 1.8rem;
  font-weight: 520;
  margin: 0;
}

.section-body {
  line-height: 1.8;
  color: #333;
}

.section-body p {
  margin-bottom: 1.2rem;
}

.section-body code {
  background: #F0F0F0;
  padding: 2px 8px;
  font-family: var(--font-mono);
  font-size: 0.85em;
  border-radius: 2px;
}

/* Feature grid */
.feature-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-top: 25px;
}

.feature-card {
  border: 1px solid var(--border);
  padding: 25px;
  transition: border-color 0.2s;
}

.feature-card:hover {
  border-color: var(--black);
}

.feature-icon {
  font-size: 1.5rem;
  margin-bottom: 12px;
  color: var(--orange);
}

.feature-title {
  font-weight: 600;
  font-size: 1rem;
  margin-bottom: 8px;
}

.feature-desc {
  font-size: 0.9rem;
  color: var(--gray-text);
  line-height: 1.6;
}

/* Steps */
.step-block {
  display: flex;
  gap: 25px;
  margin-bottom: 35px;
  padding: 25px;
  border: 1px solid var(--border);
}

.step-marker {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 1.2rem;
  width: 40px;
  height: 40px;
  border: 2px solid var(--black);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-content h3 {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 10px 0;
}

.step-content p {
  margin-bottom: 12px;
}

.tip-box {
  background: #FFFAF0;
  border-left: 3px solid var(--orange);
  padding: 12px 18px;
  font-size: 0.9rem;
  color: #555;
}

.tip-label {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.75rem;
  color: var(--orange);
  margin-right: 10px;
}

.examples-box {
  background: var(--gray-light);
  padding: 18px 22px;
  border: 1px solid var(--border);
}

.examples-title {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
  margin-bottom: 10px;
}

.examples-box ul {
  margin: 0;
  padding-left: 20px;
}

.examples-box li {
  margin-bottom: 8px;
  font-size: 0.95rem;
  color: #333;
}

/* Workflow cards */
.workflow-card {
  border: 1px solid var(--border);
  margin-bottom: 20px;
}

.wf-header {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 18px 25px;
  border-bottom: 1px solid var(--border);
  background: var(--gray-light);
}

.wf-num {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.8rem;
  color: var(--orange);
}

.wf-title {
  font-weight: 600;
  flex: 1;
}

.wf-time {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
}

.wf-body {
  padding: 20px 25px;
}

.wf-body ul {
  padding-left: 20px;
  margin: 10px 0;
}

.wf-body li {
  margin-bottom: 8px;
}

/* Format table */
.format-table {
  border: 1px solid var(--border);
}

.format-row {
  display: grid;
  grid-template-columns: 100px 1fr 1fr;
  padding: 15px 20px;
  border-bottom: 1px solid var(--border);
  font-size: 0.95rem;
}

.format-row:last-child {
  border-bottom: none;
}

.format-row.header {
  background: var(--gray-light);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
  font-weight: 600;
}

.format-ext {
  font-family: var(--font-mono);
  font-weight: 700;
}

/* Tips grid */
.tips-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.tip-card {
  border: 1px solid var(--border);
  padding: 25px;
}

.tip-card .tip-num {
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--orange);
  opacity: 0.5;
  font-size: 2rem;
  margin-bottom: 10px;
}

.tip-card h3 {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 10px 0;
}

.tip-card p {
  font-size: 0.9rem;
  color: var(--gray-text);
  line-height: 1.6;
  margin: 0;
}

/* FAQ */
.faq-list {
  border: 1px solid var(--border);
}

.faq-item {
  border-bottom: 1px solid var(--border);
}

.faq-item:last-child {
  border-bottom: none;
}

.faq-question {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 22px;
  cursor: pointer;
  font-weight: 520;
  transition: background 0.2s;
}

.faq-question:hover {
  background: var(--gray-light);
}

.faq-toggle {
  font-family: var(--font-mono);
  font-size: 1.3rem;
  color: #999;
  flex-shrink: 0;
  margin-left: 15px;
}

.faq-answer {
  padding: 0 22px 20px;
  color: var(--gray-text);
  line-height: 1.7;
}

/* Footer */
.help-footer {
  text-align: center;
  margin-top: 80px;
}

.footer-line {
  width: 60px;
  height: 2px;
  background: var(--orange);
  margin: 0 auto 25px;
}

.help-footer p {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: #999;
  margin-bottom: 15px;
}

.back-home {
  font-family: var(--font-mono);
  font-size: 0.9rem;
  color: var(--black);
  text-decoration: none;
  border-bottom: 1px solid var(--border);
  padding-bottom: 2px;
  transition: border-color 0.2s;
}

.back-home:hover {
  border-color: var(--black);
}

/* Responsive */
@media (max-width: 768px) {
  .help-title { font-size: 2.2rem; }
  .feature-grid, .tips-grid { grid-template-columns: 1fr; }
  .format-row { grid-template-columns: 80px 1fr; }
  .format-row span:last-child { display: none; }
  .format-row.header span:last-child { display: none; }
  .step-block { flex-direction: column; }
  .help-nav { gap: 3px; }
}
</style>
