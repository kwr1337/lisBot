import json
import os
from datetime import datetime, timedelta
from typing import Optional
import logging
import secrets

TOKENS_FILE = "admin_tokens.json"

# Хранилище токенов в памяти
tokens = {}

def save_tokens():
    """Сохраняет токены в файл"""
    try:
        with open(TOKENS_FILE, 'w') as f:
            # Конвертируем datetime в строки перед сохранением
            serializable_tokens = {}
            for token, data in tokens.items():
                serializable_tokens[token] = {
                    'user_id': data[0],  # user_id
                    'expires': data[1].isoformat()  # expires как строка
                }
            json.dump(serializable_tokens, f)
    except Exception as e:
        logging.error(f"Error saving tokens: {e}")

def load_tokens():
    """Загружает токены из файла"""
    global tokens
    try:
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, 'r') as f:
                data = json.load(f)
                # Конвертируем строки обратно в datetime
                tokens = {
                    token: (
                        info['user_id'],
                        datetime.fromisoformat(info['expires'])
                    )
                    for token, info in data.items()
                }
    except Exception as e:
        logging.error(f"Error loading tokens: {e}")
        tokens = {}

def generate_admin_token(user_id: int) -> str:
    """Генерирует временный токен для доступа к админ-панели"""
    token = secrets.token_urlsafe(32)
    expires = datetime.now() + timedelta(hours=24)  # Токен на 24 часа
    tokens[token] = (user_id, expires)  # Сохраняем как кортеж
    save_tokens()
    return token

def verify_token(token: str) -> Optional[int]:
    """Проверяет токен и возвращает user_id если токен валидный"""
    load_tokens()  # Загружаем актуальные токены
    
    if token not in tokens:
        return None
        
    user_id, expires = tokens[token]  # Распаковываем кортеж
    if datetime.now() > expires:  # expires уже datetime
        del tokens[token]
        save_tokens()
        return None
        
    return user_id

# Загружаем токены при импорте модуля
load_tokens()

def add_token(token: str, user_id: int, expires: datetime):
    tokens[token] = (user_id, expires)
    save_tokens()
    logging.info(f"Added token for user {user_id}, expires {expires}")

def remove_token(token: str):
    if token in tokens:
        del tokens[token]
        save_tokens()
        logging.info(f"Removed token {token}")

def verify_token(token: str) -> Optional[int]:
    if token not in tokens:
        logging.warning(f"Token {token} not found")
        return None
        
    user_id, expires = tokens[token]
    
    if datetime.now() > expires:
        logging.warning(f"Token {token} expired")
        remove_token(token)
        return None
        
    logging.info(f"Token {token} verified for user {user_id}")
    return user_id

def cleanup_expired_tokens():
    now = datetime.now()
    expired = [token for token, (_, expires) in tokens.items() if now > expires]
    for token in expired:
        remove_token(token)
    if expired:
        logging.info(f"Cleaned up {len(expired)} expired tokens")

def get_token_data(token: str) -> Optional[dict]:
    tokens = load_tokens()
    data = tokens.get(token)
    if data:
        if data[1] > datetime.now():
            return {'user_id': data[0], 'expires': data[1]}
    return None 