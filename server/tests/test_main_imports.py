"""
tests/test_main_imports.py
Смоук-тест: server/app/main.py должен хотя бы импортироваться.
Ловит SyntaxError/опечатки, которые юнит-тесты модулей не замечают
(main.py собирается только при реальном запуске uvicorn).
"""
import importlib


def test_main_module_imports():
    module = importlib.import_module("server.app.main")
    assert module.app.title == "Dental AI — Server"
