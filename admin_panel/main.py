from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from routes import router
from database.models import init_admin_logs_table
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Создаем приложение FastAPI
app = FastAPI()

# Добавляем middleware для сессий
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key",
    session_cookie="admin_session"
)

# Подключаем статические файлы
app.mount("/static", StaticFiles(directory="admin_panel/static"), name="static")

# Подключаем роутер
app.include_router(router)

@app.on_event("startup")
async def startup_event():
    logging.info("Starting application...")
    try:
        init_admin_logs_table()
        logging.info("Admin logs table check completed")
    except Exception as e:
        logging.error(f"Error during startup: {e}") 