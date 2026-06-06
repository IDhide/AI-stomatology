# ════════════════════════════════════════════════════════════════════
#  Smile.AI — Makefile (веб-киоск с голосом + тестовый DIKIDI)
#  Использование: make <target>
# ════════════════════════════════════════════════════════════════════

.PHONY: help demo demo-down demo-logs smart smart-down test lint clean

COMPOSE_DEMO = docker compose -f docker-compose.demo.yml

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

# ── Разработка ────────────────────────────────────────────────────
test: ## Тесты (dental + config)
	PYTHONPATH=. python3 -m pytest tests/ -v

lint: ## Проверка стиля (ruff, если установлен)
	ruff check src/ || true

clean: ## Очистка кэшей
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov
