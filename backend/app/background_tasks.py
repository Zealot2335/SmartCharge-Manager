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

def periodic_charge_check():
    """
    定期的充电检查任务.
    这个函数会被APScheduler周期性调用.
    """
    logger.info("--- Background Task: Running periodic check for completed charges ---")
    try:
        with get_db_session() as db:
            ChargingScheduler.check_and_finish_completed_charges(db)
        logger.info("--- Background Task: Periodic check finished successfully ---")
    except Exception as e:
        logger.error(f"--- Background Task: Error during periodic check: {e} ---", exc_info=True) 