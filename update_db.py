from database.models import init_db, check_and_update_database, update_database

if __name__ == "__main__":
    print("Инициализация и обновление базы данных...")
    init_db()  # Создаем таблицы
    check_and_update_database()  # Проверяем и обновляем структуру
    update_database()  # Добавляем новые колонки
    print("Обновление завершено!") 