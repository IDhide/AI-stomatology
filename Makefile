# ════════════════════════════════════════════════════════════════════
#  Smile.AI — Makefile (веб-киоск с голосом + тестовый DIKIDI)
#  Использование: make <target>
# ════════════════════════════════════════════════════════════════════

.PHONY: help demo demo-down demo-logs smart smart-down camera smart-camera camera-down webcam smart-webcam webcam-down qwen qwen-down full full-down test lint clean

COMPOSE_DEMO = docker compose -f docker-compose.demo.yml
COMPOSE_CAMERA = -f docker-compose.camera.yml

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ── Запуск (один рабочий вариант) ─────────────────────────────────
demo: ## Базовый стенд: голос + тестовый DIKIDI (мозг — правила) → http://localhost:8080
	$(COMPOSE_DEMO) up --build

demo-down: ## Остановить базовый стенд
	$(COMPOSE_DEMO) down

demo-logs: ## Логи стенда
	$(COMPOSE_DEMO) logs -f

smart: ## Умный стенд: + Ollama LLM (понимает контекст) → http://localhost:8080
	$(COMPOSE_DEMO) -f docker-compose.smart.yml up --build

smart-down: ## Остановить умный стенд
	$(COMPOSE_DEMO) -f docker-compose.smart.yml down

camera: ## Базовый стенд + камера (Xiaomi C200 → go2rtc → детекция лиц)
	$(COMPOSE_DEMO) $(COMPOSE_CAMERA) up --build

smart-camera: ## Умный стенд + камера (Ollama + go2rtc + детекция лиц)
	$(COMPOSE_DEMO) -f docker-compose.smart.yml $(COMPOSE_CAMERA) up --build

camera-down: ## Остановить стенд с камерой
	$(COMPOSE_DEMO) $(COMPOSE_CAMERA) down

webcam: ## Базовый стенд + USB-вебка (CAMERA_SOURCE=0, без go2rtc/облака)
	$(COMPOSE_DEMO) -f docker-compose.webcam.yml up --build

smart-webcam: ## Умный стенд + USB-вебка (Ollama + детекция лиц с /dev/video0)
	$(COMPOSE_DEMO) -f docker-compose.smart.yml -f docker-compose.webcam.yml up --build

webcam-down: ## Остановить стенд с USB-вебкой
	$(COMPOSE_DEMO) -f docker-compose.webcam.yml down

qwen: ## Умный стенд + клонированный голос (Qwen3-TTS-VC, нужен GPU + assets/voice)
	$(COMPOSE_DEMO) -f docker-compose.smart.yml -f docker-compose.qwen.yml up --build

qwen-down: ## Остановить стенд с клонированным голосом
	$(COMPOSE_DEMO) -f docker-compose.smart.yml -f docker-compose.qwen.yml down

full: ## ВСЁ: Ollama + камера (Xiaomi C200) + голос Qwen (GPU) → http://localhost:8080
	$(COMPOSE_DEMO) -f docker-compose.smart.yml $(COMPOSE_CAMERA) -f docker-compose.qwen.yml up --build

full-down: ## Остановить полный стенд
	$(COMPOSE_DEMO) -f docker-compose.smart.yml $(COMPOSE_CAMERA) -f docker-compose.qwen.yml down

# ── Разработка ────────────────────────────────────────────────────
test: ## Тесты (dental + config)
	PYTHONPATH=. python3 -m pytest tests/ -v

lint: ## Проверка стиля (ruff, если установлен)
	ruff check src/ || true

clean: ## Очистка кэшей
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov
