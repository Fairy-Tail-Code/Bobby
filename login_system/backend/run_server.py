"""
后端启动入口
使用方式: uvicorn run_server:app --reload --port 8000
"""
import uvicorn
from app.main import app

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
