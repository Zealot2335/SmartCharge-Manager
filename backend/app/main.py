import yaml
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import os
import logging
from pathlib import Path

from backend.app.api import auth, charging, billing, admin
from backend.app.services.websocket import setup_websocket
from backend.app.db.database import Base, engine
from backend.app.core.config import get_system_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该限制
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

# 静态文件服务
frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path / "static")), name="static")

# 根路径重定向到前端页面
@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = frontend_path / "index.html"
    if html_path.exists():
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>智能充电桩调度计费系统</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                .container { max-width: 800px; margin: 0 auto; }
                h1 { color: #333; }
                .api-link { margin-top: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>智能充电桩调度计费系统</h1>
                <p>系统已成功启动！</p>
                <div class="api-link">
                    <p>API文档: <a href="/docs">/docs</a></p>
                </div>
            </div>
        </body>
        </html>
        """

# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# 应用启动和关闭事件
@app.on_event("startup")
async def startup_event():
    logger.info("应用启动")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("应用关闭")

# 直接运行时的入口点
if __name__ == "__main__":
    # 获取配置
    settings = get_system_config()
    host = settings.get("host", "0.0.0.0")
    port = int(settings.get("port", 8000))
    
    # 启动服务器
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=True)