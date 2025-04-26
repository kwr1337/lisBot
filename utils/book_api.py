import requests
import logging
from typing import Optional, Dict, Any

def get_book_data_from_bibliosearch(isbn: str) -> Optional[Dict[str, Any]]:
    """
    Получает информацию о книге по ISBN через BiblioSearch API
    
    Args:
        isbn: ISBN книги
        
    Returns:
        Словарь с данными о книге или None, если книга не найдена
    """
    try:
        url = "https://bibliosearch.ru/bsapi/v1/advsearch"
        params = {"isbn": isbn}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        return None
    except Exception as e:
        logging.error(f"Ошибка при получении данных из BiblioSearch API: {e}")
        return None

def get_book_data_from_google(isbn: str) -> Optional[Dict[str, Any]]:
    """
    Получает информацию о книге по ISBN через Google Books API
    
    Args:
        isbn: ISBN книги
        
    Returns:
        Словарь с данными о книге или None, если книга не найдена
    """
    try:
        url = f"https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": f"isbn:{isbn}",
            "langRestrict": "ru"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if 'items' not in data or not data['items']:
            return None
            
        book_info = data['items'][0]['volumeInfo']
        
        # Преобразуем данные в единый формат
        return {
            "title": book_info.get('title', ''),
            "authors": ', '.join(book_info.get('authors', [])),
            "annotation": book_info.get('description', ''),
            "publisher": book_info.get('publisher', ''),
            "published": book_info.get('publishedDate', ''),
            "pageCount": book_info.get('pageCount', 0),
            "classification": {
                "isbn": isbn
            }
        }
    except Exception as e:
        logging.error(f"Ошибка при получении данных из Google Books API: {e}")
        return None

def get_book_by_isbn(isbn: str) -> Optional[Dict[str, Any]]:
    """
    Получает информацию о книге по ISBN, пробуя разные API
    
    Args:
        isbn: ISBN книги
        
    Returns:
        Словарь с данными о книге или None, если книга не найдена
    """
    # Сначала пробуем через BiblioSearch API
    book_data = get_book_data_from_bibliosearch(isbn)
    
    # Если не удалось получить данные, пробуем Google Books API
    if not book_data:
        book_data = get_book_data_from_google(isbn)
    
    return book_data 