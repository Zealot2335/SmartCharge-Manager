from typing import Dict, List, Any, Optional
from fastapi import WebSocket, FastAPI, WebSocketDisconnect
import json
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # 活动连接: {"user_id": {"client_id": WebSocket}}
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # 管理员连接: {"client_id": WebSocket}
        self.admin_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str, client_id: str):
        """用户连接"""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = {}
        self.active_connections[user_id][client_id] = websocket
        logger.info(f"用户 {user_id} 的客户端 {client_id} 已连接")
    
    async def connect_admin(self, websocket: WebSocket, client_id: str):
        """管理员连接"""
        await websocket.accept()
        self.admin_connections[client_id] = websocket
        logger.info(f"管理员客户端 {client_id} 已连接")
    
    def disconnect(self, user_id: str, client_id: str):
        """用户断开连接"""
        if user_id in self.active_connections and client_id in self.active_connections[user_id]:
            del self.active_connections[user_id][client_id]
            # 如果用户没有活动连接，删除用户条目
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
            logger.info(f"用户 {user_id} 的客户端 {client_id} 已断开连接")
    
    def disconnect_admin(self, client_id: str):
        """管理员断开连接"""
        if client_id in self.admin_connections:
            del self.admin_connections[client_id]
            logger.info(f"管理员客户端 {client_id} 已断开连接")
    
    async def send_personal_message(self, message: Dict[str, Any], user_id: str):
        """发送个人消息给特定用户的所有客户端"""
        if user_id in self.active_connections:
            # 添加时间戳
            message["timestamp"] = datetime.now().isoformat()
            for client_id, connection in self.active_connections[user_id].items():
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"发送消息给用户 {user_id} 的客户端 {client_id} 失败: {str(e)}")
    
    async def send_admin_message(self, message: Dict[str, Any]):
        """发送消息给所有管理员客户端"""
        # 添加时间戳
        message["timestamp"] = datetime.now().isoformat()
        for client_id, connection in self.admin_connections.items():
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"发送消息给管理员客户端 {client_id} 失败: {str(e)}")
    
    async def broadcast_message(self, message: Dict[str, Any]):
        """广播消息给所有连接的客户端"""
        # 添加时间戳
        message["timestamp"] = datetime.now().isoformat()
        
        # 发送给所有用户
        for user_id, clients in self.active_connections.items():
            for client_id, connection in clients.items():
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"广播消息给用户 {user_id} 的客户端 {client_id} 失败: {str(e)}")
        
        # 发送给所有管理员
        for client_id, connection in self.admin_connections.items():
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"广播消息给管理员客户端 {client_id} 失败: {str(e)}")

# 创建连接管理器实例
manager = ConnectionManager()

def setup_websocket(app: FastAPI):
    """设置WebSocket路由"""
    
    @app.websocket("/ws/user/{user_id}/{client_id}")
    async def websocket_endpoint(websocket: WebSocket, user_id: str, client_id: str):
        """用户WebSocket端点"""
        await manager.connect(websocket, user_id, client_id)
        try:
            while True:
                # 接收消息
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                    # 处理接收到的消息，可以根据需要添加更多逻辑
                    logger.debug(f"收到用户 {user_id} 的消息: {message}")
                except json.JSONDecodeError:
                    logger.error(f"无效的JSON数据: {data}")
        except WebSocketDisconnect:
            manager.disconnect(user_id, client_id)
    
    @app.websocket("/ws/admin/{client_id}")
    async def admin_websocket_endpoint(websocket: WebSocket, client_id: str):
        """管理员WebSocket端点"""
        await manager.connect_admin(websocket, client_id)
        try:
            while True:
                # 接收消息
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                    # 处理接收到的消息，可以根据需要添加更多逻辑
                    logger.debug(f"收到管理员 {client_id} 的消息: {message}")
                except json.JSONDecodeError:
                    logger.error(f"无效的JSON数据: {data}")
        except WebSocketDisconnect:
            manager.disconnect_admin(client_id)

# 辅助函数，用于在其他模块中发送消息
async def notify_charge_status_change(user_id: str, request_id: int, status: str, data: Dict[str, Any]):
    """通知充电状态变化"""
    message = {
        "type": "charge_status_change",
        "request_id": request_id,
        "status": status,
        "data": data
    }
    await manager.send_personal_message(message, user_id)
    
    # 同时通知管理员
    admin_message = {
        "type": "admin_charge_status_change",
        "user_id": user_id,
        "request_id": request_id,
        "status": status,
        "data": data
    }
    await manager.send_admin_message(admin_message)

async def notify_pile_status_change(pile_id: int, status: str, data: Dict[str, Any]):
    """通知充电桩状态变化"""
    message = {
        "type": "pile_status_change",
        "pile_id": pile_id,
        "status": status,
        "data": data
    }
    await manager.broadcast_message(message)

async def notify_queue_update(mode: str, data: Dict[str, Any]):
    """通知队列更新"""
    message = {
        "type": "queue_update",
        "mode": mode,
        "data": data
    }
    await manager.broadcast_message(message) 