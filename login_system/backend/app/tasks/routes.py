"""
Celery 任务状态查询 API（学习向）
"""
from fastapi import APIRouter, HTTPException
from celery.result import AsyncResult

from app.celery_app import celery_app
from app.schemas import TaskStatusResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    """
    查询 Celery 任务状态
    状态值：PENDING（等待中）、STARTED（已开始）、PROGRESS（进行中）、SUCCESS（成功）、FAILURE（失败）
    """
    result = AsyncResult(task_id, app=celery_app)

    response = TaskStatusResponse(
        task_id=task_id,
        status=result.status,
    )

    if result.ready():
        if result.successful():
            response.result = str(result.result)
        else:
            response.result = str(result.result) if result.result else "Task failed"
        if result.date_done:
            response.date_done = result.date_done.isoformat()
    elif result.state == "PROGRESS":
        response.result = str(result.info)

    return response


@router.get("/list")
def list_recent_tasks():
    """获取 Celery Worker 信息（学习向）"""
    inspector = celery_app.control.inspect()
    active = inspector.active()
    reserved = inspector.reserved()
    stats = inspector.stats()

    return {
        "active_tasks": active,
        "reserved_tasks": reserved,
        "worker_stats": stats,
        "message": "This endpoint shows Celery worker information for learning purposes.",
    }
