import uvicorn
from admin_panel.app import admin_app

if __name__ == "__main__":
    uvicorn.run(admin_app, host="0.0.0.0", port=8000) 