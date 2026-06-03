"""
Логирование разговоров в файл
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

from loguru import logger


class ConversationLogger:
    """Логирование разговоров с клиентами"""
    
    def __init__(self, config):
        self.enabled = config["enabled"]
        self.log_path = Path(config["path"])
        
        if self.enabled:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Логирование разговоров: {self.log_path}")
    
    def start_conversation(self) -> str:
        """Начало новой беседы"""
        conversation_id = str(uuid.uuid4())
        
        if self.enabled:
            entry = {
                "conversation_id": conversation_id,
                "event": "start",
                "timestamp": datetime.now().isoformat()
            }
            self._write_log(entry)
        
        return conversation_id
    
    def log_message(self, conversation_id: str, role: str, content: str):
        """Логирование сообщения"""
        if self.enabled:
            entry = {
                "conversation_id": conversation_id,
                "event": "message",
                "role": role,  # "user" или "assistant"
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
            self._write_log(entry)
    
    def end_conversation(self, conversation_id: str):
        """Завершение беседы"""
        if self.enabled:
            entry = {
                "conversation_id": conversation_id,
                "event": "end",
                "timestamp": datetime.now().isoformat()
            }
            self._write_log(entry)
    
    def _write_log(self, entry: dict):
        """Запись в JSONL файл"""
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"Ошибка записи лога: {e}")
