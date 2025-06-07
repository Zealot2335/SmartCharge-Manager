from sqlalchemy import Column, Integer, String, Float, Enum, DateTime, Boolean, ForeignKey, Date, Time, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime

from backend.app.db.database import Base

# 充电桩表
class ChargePile(Base):
    __tablename__ = "t_charge_pile"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False, comment="桩编号，如A、B、C等")
    type = Column(Enum("FAST", "SLOW"), nullable=False, comment="桩类型，快充或慢充")
    status = Column(Enum("AVAILABLE", "BUSY", "FAULT", "OFFLINE"), default="OFFLINE", nullable=False, comment="桩状态")
    power = Column(Float(precision=2), nullable=False, comment="充电功率 kWh/h")
    total_charge_count = Column(Integer, default=0, nullable=False, comment="累计充电次数")
    total_charge_time = Column(Integer, default=0, nullable=False, comment="累计充电时长(分钟)")
    total_charge_amount = Column(Float(precision=2), default=0.0, nullable=False, comment="累计充电度数")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # 关系
    car_requests = relationship("CarRequest", back_populates="pile")
    charge_sessions = relationship("ChargeSession", back_populates="pile")
    fault_logs = relationship("FaultLog", back_populates="pile")
    
# 充电请求表
class CarRequest(Base):
    __tablename__ = "t_car_request"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, comment="用户ID")
    queue_number = Column(String(20), unique=True, nullable=False, comment="排队号码，如F1、T2等")
    mode = Column(Enum("FAST", "SLOW"), nullable=False, comment="充电模式，快充或慢充")
    amount_kwh = Column(Float(precision=2), nullable=False, comment="请求充电量(kWh)")
    battery_capacity = Column(Float(precision=2), nullable=False, comment="电池总容量(kWh)")
    status = Column(Enum("WAITING", "QUEUING", "CHARGING", "FINISHED", "CANCELED"), default="WAITING", nullable=False, comment="请求状态")
    pile_id = Column(Integer, ForeignKey("t_charge_pile.id"), comment="分配的充电桩ID")
    queue_position = Column(Integer, comment="在充电桩队列中的位置")
    request_time = Column(DateTime, default=func.now(), nullable=False, comment="请求时间")
    start_time = Column(DateTime, comment="开始充电时间")
    end_time = Column(DateTime, comment="结束充电时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # 关系
    pile = relationship("ChargePile", back_populates="car_requests")
    charge_sessions = relationship("ChargeSession", back_populates="request")
    queue_logs = relationship("QueueLog", back_populates="request")

# 充电会话表
class ChargeSession(Base):
    __tablename__ = "t_charge_session"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("t_car_request.id"), nullable=False, comment="关联的充电请求ID")
    pile_id = Column(Integer, ForeignKey("t_charge_pile.id"), nullable=False, comment="充电桩ID")
    start_time = Column(DateTime, nullable=False, comment="会话开始时间")
    end_time = Column(DateTime, comment="会话结束时间")
    charged_kwh = Column(Float(precision=2), default=0.0, nullable=False, comment="充电电量(kWh)")
    charging_time = Column(Integer, default=0, nullable=False, comment="充电时长(分钟)")
    charge_fee = Column(Float(precision=2), default=0.0, nullable=False, comment="充电费用")
    service_fee = Column(Float(precision=2), default=0.0, nullable=False, comment="服务费用")
    total_fee = Column(Float(precision=2), default=0.0, nullable=False, comment="总费用")
    status = Column(Enum("CHARGING", "COMPLETED", "INTERRUPTED"), default="CHARGING", nullable=False, comment="会话状态")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # 关系
    request = relationship("CarRequest", back_populates="charge_sessions")
    pile = relationship("ChargePile", back_populates="charge_sessions")
    bill_details = relationship("BillDetail", back_populates="session")

# 账单主表
class BillMaster(Base):
    __tablename__ = "t_bill_master"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, comment="用户ID")
    bill_date = Column(Date, nullable=False, comment="账单日期")
    total_charge_fee = Column(Float(precision=2), default=0.0, nullable=False, comment="总充电费用")
    total_service_fee = Column(Float(precision=2), default=0.0, nullable=False, comment="总服务费用")
    total_fee = Column(Float(precision=2), default=0.0, nullable=False, comment="总费用")
    total_kwh = Column(Float(precision=2), default=0.0, nullable=False, comment="总充电量")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # 关系
    bill_details = relationship("BillDetail", back_populates="bill")

# 账单详情表
class BillDetail(Base):
    __tablename__ = "t_bill_detail"
    
    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("t_bill_master.id"), nullable=False, comment="关联的账单ID")
    session_id = Column(Integer, ForeignKey("t_charge_session.id"), nullable=False, comment="关联的充电会话ID")
    detail_number = Column(String(50), unique=True, nullable=False, comment="详单编号")
    pile_code = Column(String(10), nullable=False, comment="充电桩编号")
    charged_kwh = Column(Float(precision=2), nullable=False, comment="充电电量")
    charging_time = Column(Integer, nullable=False, comment="充电时长(分钟)")
    start_time = Column(DateTime, nullable=False, comment="启动时间")
    end_time = Column(DateTime, comment="停止时间")
    charge_fee = Column(Float(precision=2), nullable=False, comment="充电费用")
    service_fee = Column(Float(precision=2), nullable=False, comment="服务费用")
    total_fee = Column(Float(precision=2), nullable=False, comment="总费用")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # 关系
    bill = relationship("BillMaster", back_populates="bill_details")
    session = relationship("ChargeSession", back_populates="bill_details")

# 费率规则表
class RateRule(Base):
    __tablename__ = "t_rate_rule"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(Enum("PEAK", "NORMAL", "VALLEY"), nullable=False, comment="费率类型：峰时、平时、谷时")
    price = Column(Float(precision=2), nullable=False, comment="电价(元/kWh)")
    start_time = Column(Time, nullable=False, comment="开始时间")
    end_time = Column(Time, nullable=False, comment="结束时间")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

# 服务费率表
class ServiceRate(Base):
    __tablename__ = "t_service_rate"
    
    id = Column(Integer, primary_key=True, index=True)
    rate = Column(Float(precision=2), nullable=False, comment="服务费率(元/kWh)")
    effective_from = Column(DateTime, default=func.now(), nullable=False, comment="生效时间")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    is_current = Column(Boolean, default=True, nullable=False, comment="是否当前生效")

# 队列日志表
class QueueLog(Base):
    __tablename__ = "t_queue_log"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("t_car_request.id"), nullable=False, comment="充电请求ID")
    from_status = Column(String(20), nullable=False, comment="变更前状态")
    to_status = Column(String(20), nullable=False, comment="变更后状态")
    pile_id = Column(Integer, comment="充电桩ID")
    queue_position = Column(Integer, comment="队列位置")
    log_time = Column(DateTime, default=func.now(), nullable=False, comment="日志时间")
    remark = Column(String(255), comment="备注")
    
    # 关系
    request = relationship("CarRequest", back_populates="queue_logs")

# 故障日志表
class FaultLog(Base):
    __tablename__ = "t_fault_log"
    
    id = Column(Integer, primary_key=True, index=True)
    pile_id = Column(Integer, ForeignKey("t_charge_pile.id"), nullable=False, comment="充电桩ID")
    fault_time = Column(DateTime, nullable=False, comment="故障时间")
    recovery_time = Column(DateTime, comment="恢复时间")
    status = Column(Enum("ACTIVE", "RESOLVED"), default="ACTIVE", nullable=False, comment="故障状态")
    description = Column(String(255), nullable=False, comment="故障描述")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # 关系
    pile = relationship("ChargePile", back_populates="fault_logs")

# 报表数据表(日粒度)
class ReportDaily(Base):
    __tablename__ = "t_report_daily"
    
    id = Column(Integer, primary_key=True, index=True)
    report_date = Column(Date, nullable=False, comment="报表日期")
    pile_id = Column(Integer, nullable=False, comment="充电桩ID")
    pile_code = Column(String(10), nullable=False, comment="充电桩编号")
    charge_count = Column(Integer, default=0, nullable=False, comment="充电次数")
    charge_time = Column(Integer, default=0, nullable=False, comment="充电总时长(分钟)")
    charge_kwh = Column(Float(precision=2), default=0.0, nullable=False, comment="充电总电量")
    charge_fee = Column(Float(precision=2), default=0.0, nullable=False, comment="充电总费用")
    service_fee = Column(Float(precision=2), default=0.0, nullable=False, comment="服务总费用")
    total_fee = Column(Float(precision=2), default=0.0, nullable=False, comment="总费用")
    created_at = Column(DateTime, default=func.now(), nullable=False)

# 系统配置表
class Config(Base):
    __tablename__ = "t_config"
    
    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(50), unique=True, nullable=False, comment="配置键")
    config_value = Column(String(255), nullable=False, comment="配置值")
    description = Column(String(255), comment="配置描述")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

# 用户表
class User(Base):
    __tablename__ = "t_user"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), unique=True, nullable=False, comment="用户ID")
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    password = Column(String(255), nullable=False, comment="密码")
    role = Column(Enum("USER", "ADMIN"), default="USER", nullable=False, comment="角色")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False) 