"""
FastAPI 应用入口
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.database import init_db
from app.tasks.routes import router as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的操作"""
    # 启动时：初始化数据库
    init_db()
    print("✅ Database initialized")
    yield
    # 关闭时的清理操作
    print("👋 Application shutting down")


app = FastAPI(
    title="Celery + Redis Login System",
    description="学习型登录系统 - 演示 Celery + Redis 异步任务队列在用户认证中的应用",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")


@app.get("/")
def root():
    return {
        "message": "Celery + Redis Login System API",
        "docs": "/docs",
    }
