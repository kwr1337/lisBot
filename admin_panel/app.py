from fastapi import FastAPI
from fastapi.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
from admin_panel.routes import router

# Создаем приложение для веб-панели
admin_app = FastAPI()

# Добавляем middleware
admin_app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

# Подключаем статические файлы
admin_app.mount("/static", StaticFiles(directory="admin_panel/static"), name="static")

# Подключаем роутер
admin_app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(admin_app, host="0.0.0.0", port=8000) 