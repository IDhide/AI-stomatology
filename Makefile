# ════════════════════════════════════════════════════════════════════
#  Smile.AI — Makefile
#  Использование: make <target>
# ════════════════════════════════════════════════════════════════════

.PHONY: help setup setup-gpu setup-dev run run-sim run-window prod \
        docker docker-gpu docker-down lint test clean

help: ## Показать этот список
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Установка окружения ────────────────────────────────────────────
setup: ## Установка CPU-окружения через uv
	bash scripts/setup_env.sh cpu

setup-gpu: ## Установка GPU-окружения (CUDA 12.1)
	bash scripts/setup_env.sh gpu

setup-dev: ## Установка dev-окружения (+ ruff/pytest)
	bash scripts/setup_env.sh dev

# ── Запуск ────────────────────────────────────────────────────────
run: ## Оффлайн-демо без камеры
	bash scripts/run.sh offline

run-sim: ## Оффлайн с симуляцией голоса (stdin)
	bash scripts/run.sh offline-sim

run-window: ## Оффлайн в оконном режиме
	bash scripts/run.sh offline-window

prod: ## Production-запуск (нужны Ollama + DIKIDI)
	bash scripts/run.sh prod

# ── Docker ────────────────────────────────────────────────────────
docker: ## Сборка и запуск через Docker (CPU)
	bash scripts/run.sh docker

docker-gpu: ## Сборка и запуск через Docker (GPU)
	bash scripts/run.sh docker-gpu

docker-down: ## Остановить Docker-контейнеры
	bash scripts/run.sh docker-down

# ── Разработка ────────────────────────────────────────────────────
lint: ## Проверка кода (ruff)
	.venv/bin/ruff check src/

lint-fix: ## Автоисправление стиля
	.venv/bin/ruff check --fix src/

test: ## Запуск тестов
	.venv/bin/pytest tests/ -v

# ── Утилиты ───────────────────────────────────────────────────────
clean: ## Очистка временных файлов
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov
