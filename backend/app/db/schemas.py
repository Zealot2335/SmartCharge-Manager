from pydantic import BaseModel, Field, validator
from typing import List, Optional, Union, Dict, Any
from datetime import datetime, date, time
from enum import Enum

# 枚举类型
class ChargeMode(str, Enum):
    FAST = "FAST"  # 快充
    SLOW = "SLOW"  # 慢充

class PileStatus(str, Enum):
    AVAILABLE = "AVAILABLE"  # 可用
    BUSY = "BUSY"  # 忙碌
    FAULT = "FAULT"  # 故障
    OFFLINE = "OFFLINE"  # 离线

class RequestStatus(str, Enum):
    WAITING = "WAITING"  # 等候区等待
    QUEUING = "QUEUING"  # 充电区排队
    CHARGING = "CHARGING"  # 充电中
    FINISHED = "FINISHED"  # 已完成
    CANCELED = "CANCELED"  # 已取消

class SessionStatus(str, Enum):
    CHARGING = "CHARGING"  # 充电中
    COMPLETED = "COMPLETED"  # 已完成
    INTERRUPTED = "INTERRUPTED"  # 已中断

class RateType(str, Enum):
    PEAK = "PEAK"  # 峰时
    NORMAL = "NORMAL"  # 平时
    VALLEY = "VALLEY"  # 谷时

class FaultStatus(str, Enum):
    ACTIVE = "ACTIVE"  # 活跃
    RESOLVED = "RESOLVED"  # 已解决

class UserRole(str, Enum):
    USER = "USER"  # 用户
    ADMIN = "ADMIN"  # 管理员

# 基础模型
class TimeStampModel(BaseModel):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

# 用户模型
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str
    user_id: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserInDB(UserBase, TimeStampModel):
    id: int
    user_id: str
    role: UserRole

class User(UserInDB):
    pass

class Token(BaseModel):
    access_token: str
    token_type: str
    role: UserRole

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[UserRole] = None

# 充电桩模型
class ChargePileBase(BaseModel):
    code: str
    type: ChargeMode
    power: float

class ChargePileCreate(ChargePileBase):
    pass

class ChargePileUpdate(BaseModel):
    status: Optional[PileStatus] = None

class ChargePileInDB(ChargePileBase, TimeStampModel):
    id: int
    status: PileStatus
    total_charge_count: int
    total_charge_time: int
    total_charge_amount: float

class ChargePile(ChargePileInDB):
    pass

class ChargePileDetail(ChargePile):
    queue_length: int = 0
    charging_car: Optional[Dict[str, Any]] = None
    queuing_cars: List[Dict[str, Any]] = []

# 充电请求模型
class ChargeRequestBase(BaseModel):
    mode: ChargeMode
    amount_kwh: float
    battery_capacity: float

class ChargeRequestCreate(ChargeRequestBase):
    pass

class ChargeRequestUpdate(BaseModel):
    mode: Optional[ChargeMode] = None
    amount_kwh: Optional[float] = None

class ChargeRequestInDB(ChargeRequestBase, TimeStampModel):
    id: int
    user_id: str
    queue_number: str
    status: RequestStatus
    pile_id: Optional[int] = None
    queue_position: Optional[int] = None
    request_time: datetime
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

class ChargeRequest(ChargeRequestInDB):
    pile: Optional[ChargePile] = None

class ChargeRequestDetail(ChargeRequest):
    wait_count: int = 0  # 等待人数
    estimated_wait_time: Optional[float] = None  # 预计等待时间(分钟)
    estimated_finish_time: Optional[datetime] = None  # 预计完成时间
    pile_code: Optional[str] = None  # 充电桩编号
    charging_minutes: Optional[float] = None  # 充电时长(分钟)
    charged_kwh: Optional[float] = None  # 已充电量(kWh)
    remaining_minutes: Optional[float] = None  # 剩余时间(分钟)
    progress: Optional[float] = None  # 充电进度(%)
    session_id: Optional[int] = None  # 会话ID

    class Config:
        from_attributes = True
        # 添加自定义处理
        @classmethod
        def from_orm(cls, obj):
            # 首先使用标准方法处理基础属性
            instance = super().from_orm(obj)
            
            # 确保额外属性有默认值
            if instance.wait_count is None:
                instance.wait_count = 0
            if instance.charged_kwh is None:
                instance.charged_kwh = 0.0
            if instance.progress is None:
                instance.progress = 0.0
                
            return instance

# 充电会话模型
class ChargeSessionBase(BaseModel):
    request_id: int
    pile_id: int
    start_time: datetime

class ChargeSessionCreate(ChargeSessionBase):
    pass

class ChargeSessionUpdate(BaseModel):
    end_time: Optional[datetime] = None
    charged_kwh: Optional[float] = None
    charging_time: Optional[int] = None
    charge_fee: Optional[float] = None
    service_fee: Optional[float] = None
    total_fee: Optional[float] = None
    status: Optional[SessionStatus] = None

class ChargeSessionInDB(ChargeSessionBase, TimeStampModel):
    id: int
    end_time: Optional[datetime] = None
    charged_kwh: float
    charging_time: int
    charge_fee: float
    service_fee: float
    total_fee: float
    status: SessionStatus

class ChargeSession(ChargeSessionInDB):
    pile: Optional[ChargePile] = None
    request: Optional[ChargeRequest] = None

# 账单模型
class BillMasterBase(BaseModel):
    user_id: str
    bill_date: date

class BillMasterCreate(BillMasterBase):
    total_charge_fee: float
    total_service_fee: float
    total_fee: float
    total_kwh: float

class BillMasterInDB(BillMasterBase, TimeStampModel):
    id: int
    total_charge_fee: float
    total_service_fee: float
    total_fee: float
    total_kwh: float

class BillMaster(BillMasterInDB):
    pass

class BillDetailBase(BaseModel):
    bill_id: int
    session_id: int
    detail_number: str
    pile_code: str
    charged_kwh: float
    charging_time: int
    start_time: datetime
    end_time: Optional[datetime] = None
    charge_fee: float
    service_fee: float
    total_fee: float

class BillDetailCreate(BillDetailBase):
    pass

class BillDetailInDB(BillDetailBase, TimeStampModel):
    id: int

class BillDetail(BillDetailInDB):
    pass

# 费率规则模型
class RateRuleBase(BaseModel):
    type: RateType
    price: float
    start_time: time
    end_time: time

class RateRuleCreate(RateRuleBase):
    pass

class RateRuleUpdate(BaseModel):
    price: Optional[float] = None

class RateRuleInDB(RateRuleBase, TimeStampModel):
    id: int

class RateRule(RateRuleInDB):
    pass

# 服务费率模型
class ServiceRateBase(BaseModel):
    rate: float

class ServiceRateCreate(ServiceRateBase):
    pass

class ServiceRateInDB(ServiceRateBase, TimeStampModel):
    id: int
    effective_from: datetime
    is_current: bool

class ServiceRate(ServiceRateInDB):
    pass

# 故障日志模型
class FaultLogBase(BaseModel):
    pile_id: int
    fault_time: datetime
    description: str

class FaultLogCreate(FaultLogBase):
    pass

class FaultLogUpdate(BaseModel):
    recovery_time: Optional[datetime] = None
    status: Optional[FaultStatus] = None

class FaultLogInDB(FaultLogBase, TimeStampModel):
    id: int
    recovery_time: Optional[datetime] = None
    status: FaultStatus

class FaultLog(FaultLogInDB):
    pile: Optional[ChargePile] = None

# 报表模型
class ReportDailyBase(BaseModel):
    report_date: date
    pile_id: int
    pile_code: str

class ReportDailyCreate(ReportDailyBase):
    charge_count: int
    charge_time: int
    charge_kwh: float
    charge_fee: float
    service_fee: float
    total_fee: float

class ReportDailyInDB(ReportDailyCreate, TimeStampModel):
    id: int

class ReportDaily(ReportDailyInDB):
    pass

# 系统配置模型
class ConfigBase(BaseModel):
    config_key: str
    config_value: str
    description: Optional[str] = None

class ConfigCreate(ConfigBase):
    pass

class ConfigUpdate(BaseModel):
    config_value: str

class ConfigInDB(ConfigBase, TimeStampModel):
    id: int

class Config(ConfigInDB):
    pass

# WebSocket 消息模型
class WSMessage(BaseModel):
    type: str
    data: Dict[str, Any] 