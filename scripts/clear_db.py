from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_db_url

def clear_database_tables():
    """
    清空数据库中的 CarRequest 和 QueueLog 表，并重置充电桩状态。
    如果表不存在，则跳过。
    """
    db_url = get_db_url()
    engine = create_engine(db_url)
    inspector = inspect(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    
    try:
        print("开始清空数据表...")
        
        # 检查并清空 queue_log 表
        if inspector.has_table("queue_log"):
            db.execute(text("DELETE FROM queue_log;"))
            print("已清空 queue_log 表。")
        else:
            print("queue_log 表不存在，跳过。")

        # 检查并清空 car_request 表
        if inspector.has_table("car_request"):
            db.execute(text("DELETE FROM car_request;"))
            print("已清空 car_request 表。")
        else:
            print("car_request 表不存在，跳过。")
            
        # 检查并重置 charge_pile 表
        if inspector.has_table("charge_pile"):
            db.execute(text("UPDATE charge_pile SET status = 'AVAILABLE';"))
            print("已重置所有充电桩状态为 'AVAILABLE'。")
        else:
            print("charge_pile 表不存在，跳过。")
            
        db.commit()
        print("数据库清理完成！")
        
    except Exception as e:
        print(f"清理数据库时发生错误: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    clear_database_tables() 