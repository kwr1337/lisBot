from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from routes import router
from database.models import init_admin_logs_table
import logging
from routes import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")
app.mount("/static", StaticFiles(directory="admin_panel/static"), name="static")
app.include_router(router)
app.include_router(admin_router, prefix="/admin")

@app.on_event("startup")
async def startup_event():
    logging.info("Starting application...")
    try:
        init_admin_logs_table()
        logging.info("Admin logs table check completed")
    except Exception as e:
        logging.error(f"Error during startup: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 