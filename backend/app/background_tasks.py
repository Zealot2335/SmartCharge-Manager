"""
后台任务定义
"""
import logging
from sqlalchemy.orm import Session
from contextlib import contextmanager

from backend.app.db.database import SessionLocal
from backend.app.services.scheduler import ChargingScheduler

logger = logging.getLogger(__name__)

@contextmanager
def get_db_session():
    """Provide a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def periodic_charge_check(db: Session):
    """
    定期检查并处理已完成的充电请求
    这是系统的主调度循环，每隔一段时间会自动执行
    """
    try:
        logger.info("--- 后台任务: 运行定期充电检查 ---")
        
        # 每次运行前先确保数据状态一致
        ChargingScheduler.fix_pile_charging_status(db)
        
        # 检查并自动完成已达到请求量的充电任务
        scheduler = ChargingScheduler()
        scheduler.check_and_finish_completed_charges(db)
        
        # 从等候区召唤车辆
        scheduler.check_and_call_waiting_cars(db)
        
    except Exception as e:
        logger.error(f"--- 后台任务: 定期检查期间发生错误: {e} ---", exc_info=True) 