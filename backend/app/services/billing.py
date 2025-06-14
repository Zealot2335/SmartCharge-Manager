from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime, time, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import uuid
import logging

from backend.app.db.models import (
    ChargeSession, CarRequest, ChargePile, BillMaster, BillDetail,
    RateRule, ServiceRate
)
from backend.app.db.schemas import SessionStatus
from backend.app.core.config import get_station_config

logger = logging.getLogger(__name__)

class BillingService:
    """计费服务，处理充电计费和账单生成"""
    
    @staticmethod
    def get_current_service_rate(db: Session) -> float:
        """获取当前服务费率"""
        # 从数据库获取当前服务费率
        service_rate = db.query(ServiceRate).filter(ServiceRate.is_current == True).first()
        if service_rate:
            return service_rate.rate
            
        # 从配置获取默认费率
        config = get_station_config()
        return config.get("ServiceRate", 0.8)
    
    @staticmethod
    def get_rate_by_time(db: Session, charge_time: datetime) -> float:
        """根据充电时间获取对应费率"""
        # 提取时间部分
        time_part = charge_time.time()
        
        # 查询匹配的费率规则
        rate_rule = db.query(RateRule).filter(
            and_(
                RateRule.start_time <= time_part,
                RateRule.end_time >= time_part
            )
        ).first()
        
        # 特殊处理跨天的谷时段 (23:00~次日7:00)
        if not rate_rule:
            valley_night = db.query(RateRule).filter(
                and_(
                    RateRule.type == "VALLEY",
                    RateRule.start_time >= time(23, 0),
                    RateRule.end_time <= time(23, 59)
                )
            ).first()
            
            valley_morning = db.query(RateRule).filter(
                and_(
                    RateRule.type == "VALLEY",
                    RateRule.start_time >= time(0, 0),
                    RateRule.end_time <= time(7, 0)
                )
            ).first()
            
            if valley_night and time_part >= valley_night.start_time:
                return valley_night.price
            elif valley_morning and time_part <= valley_morning.end_time:
                return valley_morning.price
        
        # 默认返回平时费率
        return rate_rule.price if rate_rule else 0.7
    
    @staticmethod
    def calculate_charging_cost(
        db: Session, 
        start_time: datetime, 
        end_time: datetime, 
        amount_kwh: float
    ) -> Tuple[float, float, float]:
        """
        计算充电费用
        返回：(充电费, 服务费, 总费用)
        """
        if not end_time:
            end_time = datetime.now()
            
        # 充电时间间隔(分钟)
        charging_minutes = (end_time - start_time).total_seconds() / 60
        
        # 获取服务费率
        service_rate = BillingService.get_current_service_rate(db)
        
        # 计算服务费
        service_fee = amount_kwh * service_rate
        
        # 初始化充电费
        charge_fee = 0.0
        
        # 计算充电费 - 按小时计算，处理跨时段情况
        current_time = start_time
        remaining_kwh = amount_kwh
        
        # 计算每小时充电量
        hour_delta = timedelta(hours=1)
        
        while current_time < end_time and remaining_kwh > 0:
            next_hour = min(current_time + hour_delta, end_time)
            
            # 这个小时的时长(小时)
            hour_fraction = (next_hour - current_time).total_seconds() / 3600
            
            # 这个小时的充电量
            hour_kwh = min(remaining_kwh, amount_kwh * hour_fraction / (charging_minutes / 60))
            
            # 获取这个小时的费率
            rate = BillingService.get_rate_by_time(db, current_time)
            
            # 计算这个小时的费用
            charge_fee += hour_kwh * rate
            
            # 更新剩余充电量和当前时间
            remaining_kwh -= hour_kwh
            current_time = next_hour
        
        # 计算总费用
        total_fee = charge_fee + service_fee
        
        return charge_fee, service_fee, total_fee
    
    @staticmethod
    def create_charge_session(
        db: Session, request_id: int, pile_id: int
    ) -> Optional[ChargeSession]:
        """创建充电会话"""
        # 检查请求是否存在
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            return None
            
        # 创建会话
        session = ChargeSession(
            request_id=request_id,
            pile_id=pile_id,
            start_time=datetime.now(),
            charged_kwh=0.0,
            charging_time=0,
            charge_fee=0.0,
            service_fee=0.0,
            total_fee=0.0,
            status=SessionStatus.CHARGING
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        
        return session
    
    @staticmethod
    def complete_charge_session(
        db: Session, session_id: int, charged_kwh: Optional[float] = None
    ) -> Optional[ChargeSession]:
        """完成充电会话，计算费用"""
        # 获取会话
        session = db.query(ChargeSession).filter(ChargeSession.id == session_id).first()
        if not session:
            return None
            
        # 设置结束时间
        session.end_time = datetime.now()
        
        # 获取请求信息
        request = db.query(CarRequest).filter(CarRequest.id == session.request_id).first()
        if not request:
            return None
            
        # 设置充电量
        if charged_kwh is not None:
            session.charged_kwh = charged_kwh
        else:
            # 如果没有提供充电量，使用请求的充电量
            session.charged_kwh = request.amount_kwh
            
        # 计算充电时间(分钟)
        charging_minutes = (session.end_time - session.start_time).total_seconds() / 60
        session.charging_time = int(charging_minutes)
        
        # 计算费用
        charge_fee, service_fee, total_fee = BillingService.calculate_charging_cost(
            db, session.start_time, session.end_time, session.charged_kwh
        )
        
        session.charge_fee = charge_fee
        session.service_fee = service_fee
        session.total_fee = total_fee
        session.status = SessionStatus.COMPLETED
        
        # 更新充电桩统计信息
        pile = db.query(ChargePile).filter(ChargePile.id == session.pile_id).first()
        if pile:
            pile.total_charge_count += 1
            pile.total_charge_time += session.charging_time
            pile.total_charge_amount += session.charged_kwh
        
        db.commit()
        db.refresh(session)
        
        # 生成详单
        BillingService.generate_bill_detail(db, session.id)
        
        return session
    
    @staticmethod
    def interrupt_charge_session(
        db: Session, session_id: int, charged_kwh: Optional[float] = None
    ) -> Optional[ChargeSession]:
        """中断充电会话，计算已充电费用"""
        # 获取会话
        session = db.query(ChargeSession).filter(ChargeSession.id == session_id).first()
        if not session:
            return None
            
        # 设置结束时间
        session.end_time = datetime.now()
        
        # 设置充电量
        if charged_kwh is not None:
            session.charged_kwh = charged_kwh
        else:
            # 如果没有提供充电量，根据时间比例计算
            request = db.query(CarRequest).filter(CarRequest.id == session.request_id).first()
            pile = db.query(ChargePile).filter(ChargePile.id == session.pile_id).first()
            
            if request and pile:
                # 计算充电时间(小时)
                charging_hours = (session.end_time - session.start_time).total_seconds() / 3600
                # 估算充电量
                session.charged_kwh = min(request.amount_kwh, pile.power * charging_hours)
            
        # 计算充电时间(分钟)
        charging_minutes = (session.end_time - session.start_time).total_seconds() / 60
        session.charging_time = int(charging_minutes)
        
        # 计算费用
        charge_fee, service_fee, total_fee = BillingService.calculate_charging_cost(
            db, session.start_time, session.end_time, session.charged_kwh
        )
        
        session.charge_fee = charge_fee
        session.service_fee = service_fee
        session.total_fee = total_fee
        session.status = SessionStatus.INTERRUPTED
        
        # 更新充电桩统计信息
        pile = db.query(ChargePile).filter(ChargePile.id == session.pile_id).first()
        if pile:
            pile.total_charge_count += 1
            pile.total_charge_time += session.charging_time
            pile.total_charge_amount += session.charged_kwh
        
        db.commit()
        db.refresh(session)
        
        # 生成详单
        BillingService.generate_bill_detail(db, session.id)
        
        return session
    
    @staticmethod
    def generate_bill_detail(db: Session, session_id: int) -> Optional[BillDetail]:
        """生成充电详单"""
        # 获取会话
        session = db.query(ChargeSession).filter(ChargeSession.id == session_id).first()
        if not session or not session.end_time:
            return None
            
        # 获取请求和充电桩信息
        request = db.query(CarRequest).filter(CarRequest.id == session.request_id).first()
        pile = db.query(ChargePile).filter(ChargePile.id == session.pile_id).first()
        
        if not request or not pile:
            return None
            
        # 获取或创建日账单
        bill_date = session.start_time.date()
        
        bill_master = db.query(BillMaster).filter(
            and_(
                BillMaster.user_id == request.user_id,
                BillMaster.bill_date == bill_date
            )
        ).first()
        
        if not bill_master:
            bill_master = BillMaster(
                user_id=request.user_id,
                bill_date=bill_date,
                total_charge_fee=0.0,
                total_service_fee=0.0,
                total_fee=0.0,
                total_kwh=0.0
            )
            db.add(bill_master)
            db.commit()
            db.refresh(bill_master)
            
        # 生成详单编号
        detail_number = f"D{bill_date.strftime('%Y%m%d')}{session_id:06d}"
        
        # 创建详单
        bill_detail = BillDetail(
            bill_id=bill_master.id,
            session_id=session.id,
            detail_number=detail_number,
            pile_code=pile.code,
            charged_kwh=session.charged_kwh,
            charging_time=session.charging_time,
            start_time=session.start_time,
            end_time=session.end_time,
            charge_fee=session.charge_fee,
            service_fee=session.service_fee,
            total_fee=session.total_fee
        )
        
        db.add(bill_detail)
        
        # 更新日账单
        bill_master.total_charge_fee += session.charge_fee
        bill_master.total_service_fee += session.service_fee
        bill_master.total_fee += session.total_fee
        bill_master.total_kwh += session.charged_kwh
        
        db.commit()
        db.refresh(bill_detail)
        
        return bill_detail
    
    @staticmethod
    def get_user_bill(db: Session, user_id: str, bill_date: date) -> Optional[Dict[str, Any]]:
        """获取用户指定日期的账单"""
        # 获取日账单
        bill_master = db.query(BillMaster).filter(
            and_(
                BillMaster.user_id == user_id,
                BillMaster.bill_date == bill_date
            )
        ).first()
        
        if not bill_master:
            return None
            
        # 获取详单列表
        bill_details = (
            db.query(BillDetail)
            .filter(BillDetail.bill_id == bill_master.id)
            .all()
        )
        
        # 转换为字典
        result = {
            "bill_date": bill_master.bill_date,
            "total_charge_fee": bill_master.total_charge_fee,
            "total_service_fee": bill_master.total_service_fee,
            "total_fee": bill_master.total_fee,
            "total_kwh": bill_master.total_kwh,
            "details": []
        }
        
        for detail in bill_details:
            result["details"].append({
                "detail_number": detail.detail_number,
                "pile_code": detail.pile_code,
                "charged_kwh": detail.charged_kwh,
                "charging_time": detail.charging_time,
                "start_time": detail.start_time,
                "end_time": detail.end_time,
                "charge_fee": detail.charge_fee,
                "service_fee": detail.service_fee,
                "total_fee": detail.total_fee
            })
            
        return result
    
    @staticmethod
    def get_bill_detail(db: Session, detail_id: int) -> Optional[BillDetail]:
        """获取详单信息"""
        return db.query(BillDetail).filter(BillDetail.id == detail_id).first()
    
    @staticmethod
    def get_bill_detail_by_number(db: Session, detail_number: str) -> Optional[BillDetail]:
        """根据详单编号获取详单信息"""
        return db.query(BillDetail).filter(BillDetail.detail_number == detail_number).first() 