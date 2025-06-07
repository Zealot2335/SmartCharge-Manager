from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from backend.app.core.config import get_db_url

# 创建SQLAlchemy引擎
engine = create_engine(
    get_db_url(),
    pool_pre_ping=True,  # 自动检测断开的连接
    pool_recycle=3600,  # 1小时后回收连接
    echo=False  # 设置为True可以查看SQL语句
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建Base类，所有的模型类都继承自它
Base = declarative_base()

# 依赖函数，用于获取数据库会话
def get_db() -> Session:
    """
    获取数据库会话，在FastAPI依赖注入中使用
    
    用法:
    ```
    @app.get("/items/")
    def read_items(db: Session = Depends(get_db)):
        return db.query(Item).all()
    ```
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 