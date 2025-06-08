import yaml
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import os
import logging
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.api import auth, charging, billing, admin
from backend.app.services.websocket import setup_websocket
from backend.app.db.database import Base, engine
from backend.app.core.config import get_system_config, get_db_url
from backend.app.background_tasks import periodic_charge_check

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)

# 创建数据库表（如果不存在）
Base.metadata.create_all(bind=engine)

# 创建FastAPI应用
app = FastAPI(
    title="智能充电桩调度计费系统",
    description="提供充电桩调度、充电过程管理、计费和报表功能的API",
    version="1.0.0"
)

# 配置CORS
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 设置WebSocket
setup_websocket(app)

# 包含API路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(charging.router, prefix="/api/charging", tags=["充电"])
app.include_router(billing.router, prefix="/api/billing", tags=["账单"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理"])

# 静态文件服务 (修复后)
# 将整个 frontend 目录挂载到根路径，以便能访问到 login.html, index.html 等
frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
else:
    logger.warning(f"Frontend path does not exist: {frontend_path}")

# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# 应用启动和关闭事件
@app.on_event("startup")
async def startup_event():
    # 启动后台调度器
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(periodic_charge_check, 'interval', seconds=10, id="charge_check_job")
    scheduler.start()
    app.state.scheduler = scheduler
    
    db_url = get_db_url()
    logger.info(f"应用启动，连接到数据库: {db_url}")
    logger.info("后台定时任务已启动，每10秒检查一次充电完成情况。")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("应用关闭")
    if app.state.scheduler.running:
        app.state.scheduler.shutdown()
        logger.info("后台定时任务已关闭。")

# 直接运行时的入口点
if __name__ == "__main__":
    # 获取配置
    settings = get_system_config()
    host = settings.get("host", "0.0.0.0")
    port = int(settings.get("port", 8000))
    
    # 启动服务器
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=True)