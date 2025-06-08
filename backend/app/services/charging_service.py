from typing import Dict, Tuple, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from backend.app.db.models import ChargePile, CarRequest, ChargeSession, BillDetail, BillMaster
from backend.app.db.schemas import RequestStatus, ChargeMode
from backend.app.services.scheduler import ChargingScheduler
from backend.app.services.billing import BillingService
from backend.app.core.config import get_station_config

logger = logging.getLogger(__name__)

class ChargingService:
    """充电服务，处理充电过程中的业务逻辑"""
    
    @staticmethod
    def create_charge_session(db: Session, request_id: int) -> Tuple[bool, str, Optional[ChargeSession]]:
        """
        创建充电会话
        在充电开始时调用，创建一个新的充电会话记录
        """
        # 查询充电请求
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            return False, "充电请求不存在", None
            
        if request.status != RequestStatus.CHARGING:
            return False, f"充电请求状态错误: {request.status}", None
            
        if not request.pile_id:
            return False, "充电请求未分配充电桩", None
            
        # 查询充电桩
        pile = db.query(ChargePile).filter(ChargePile.id == request.pile_id).first()
        if not pile:
            return False, "充电桩不存在", None
            
        # 创建充电会话
        session = ChargeSession(
            request_id=request.id,
            pile_id=request.pile_id,
            start_time=request.start_time or datetime.now(),
            status="CHARGING"
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        
        logger.info(f"创建充电会话: 请求ID={request_id}, 会话ID={session.id}")
        return True, "成功创建充电会话", session
    
    @staticmethod
    def update_charge_session(db: Session, session_id: int, charged_kwh: float, charging_time: int) -> Tuple[bool, str]:
        """
        更新充电会话
        在充电过程中定期调用，更新已充电量和充电时间
        """
        # 查询充电会话
        session = db.query(ChargeSession).filter(ChargeSession.id == session_id).first()
        if not session:
            return False, "充电会话不存在"
            
        if session.status != "CHARGING":
            return False, f"充电会话状态错误: {session.status}"
            
        # 更新充电量和充电时间
        session.charged_kwh = charged_kwh
        session.charging_time = charging_time
        
        db.commit()
        return True, "成功更新充电会话"
    
    @staticmethod
    def finish_charge_session(db: Session, session_id: int, charged_kwh: float, charging_time: int) -> Tuple[bool, str, Optional[BillDetail]]:
        """
        完成充电会话
        在充电结束时调用，计算费用并生成账单
        """
        # 查询充电会话
        session = db.query(ChargeSession).filter(ChargeSession.id == session_id).first()
        if not session:
            return False, "充电会话不存在", None
            
        if session.status != "CHARGING":
            return False, f"充电会话状态错误: {session.status}", None
            
        # 查询充电请求
        request = db.query(CarRequest).filter(CarRequest.id == session.request_id).first()
        if not request:
            return False, "充电请求不存在", None
            
        # 查询充电桩
        pile = db.query(ChargePile).filter(ChargePile.id == session.pile_id).first()
        if not pile:
            return False, "充电桩不存在", None
            
        # 更新充电会话
        session.charged_kwh = charged_kwh
        session.charging_time = charging_time
        session.end_time = datetime.now()
        session.status = "COMPLETED"
        
        # 计算费用
        charge_fee, service_fee, total_fee = BillingService.calculate_charging_cost(
            db, 
            session.start_time, 
            session.end_time, 
            charged_kwh
        )
        
        session.charge_fee = charge_fee
        session.service_fee = service_fee
        session.total_fee = total_fee
        
        # 更新充电桩统计信息
        pile.total_charge_count += 1
        pile.total_charge_time += charging_time
        pile.total_charge_amount += charged_kwh
        
        # 完成充电请求
        success, message = ChargingScheduler.finish_charging(db, request.id)
        if not success:
            return False, message, None
            
        # 生成账单
        bill_detail = ChargingService.generate_bill(db, session)
        if not bill_detail:
            return False, "生成账单失败", None
            
        db.commit()
        logger.info(f"完成充电会话: 会话ID={session_id}, 充电量={charged_kwh}kWh, 充电时间={charging_time}分钟, 费用={total_fee}元")
        return True, "成功完成充电会话", bill_detail
    
    @staticmethod
    def generate_bill(db: Session, session: ChargeSession) -> Optional[BillDetail]:
        """
        生成账单和详单
        """
        try:
            # 查询充电请求
            request = db.query(CarRequest).filter(CarRequest.id == session.request_id).first()
            if not request:
                logger.error(f"生成账单失败: 充电请求不存在, 会话ID={session.id}")
                return None
                
            # 查询充电桩
            pile = db.query(ChargePile).filter(ChargePile.id == session.pile_id).first()
            if not pile:
                logger.error(f"生成账单失败: 充电桩不存在, 会话ID={session.id}")
                return None
                
            # 生成详单编号 (格式: 日期+会话ID, 如: 20230601-123)
            detail_number = f"{datetime.now().strftime('%Y%m%d')}-{session.id}"
            
            # 查询或创建当日账单
            bill_date = datetime.now().date()
            bill = db.query(BillMaster).filter(
                BillMaster.user_id == request.user_id,
                BillMaster.bill_date == bill_date
            ).first()
            
            if not bill:
                # 创建新账单
                bill = BillMaster(
                    user_id=request.user_id,
                    bill_date=bill_date,
                    total_charge_fee=session.charge_fee,
                    total_service_fee=session.service_fee,
                    total_fee=session.total_fee,
                    total_kwh=session.charged_kwh
                )
                db.add(bill)
                db.flush()  # 获取ID但不提交事务
            else:
                # 更新账单总额
                bill.total_charge_fee += session.charge_fee
                bill.total_service_fee += session.service_fee
                bill.total_fee += session.total_fee
                bill.total_kwh += session.charged_kwh
            
            # 创建详单
            bill_detail = BillDetail(
                bill_id=bill.id,
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
            
            return bill_detail
        except Exception as e:
            logger.error(f"生成账单异常: {str(e)}")
            return None
    
    @staticmethod
    def get_charging_status(db: Session, request_id: int) -> Dict:
        """
        获取充电状态
        返回充电进度、已充电量、已充电时间等信息
        """
        logger = logging.getLogger(__name__)
        logger.info(f"获取充电状态: 请求ID={request_id}")
        
        # 查询充电请求
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            logger.warning(f"充电请求不存在: ID={request_id}")
            return {"error": "充电请求不存在", "status": "ERROR"}
            
        # 基本信息
        result = {
            "request_id": request.id,
            "status": request.status,
            "mode": request.mode,
            "amount_kwh": request.amount_kwh,
            "progress": 0,  # 添加默认值
            "charging_progress": 0,  # 添加默认值
            "charged_kwh": 0,  # 添加默认值
            "remaining_kwh": request.amount_kwh,  # 添加默认值
            "charging_minutes": 0,  # 添加默认值
            "estimated_remaining_minutes": 0,  # 添加默认值
            "estimated_fee": 0  # 添加默认值
        }
        
        # 如果正在充电，计算充电进度
        if request.status == RequestStatus.CHARGING and request.start_time:
            logger.info(f"处理充电中请求: ID={request_id}")
            # 查询充电桩
            pile = db.query(ChargePile).filter(ChargePile.id == request.pile_id).first()
            if pile:
                result["pile_code"] = pile.code
                result["pile_power"] = pile.power
                
                # 计算已充电时间(分钟)
                charging_minutes = (datetime.now() - request.start_time).total_seconds() / 60
                result["charging_minutes"] = charging_minutes
                
                # 估算已充电量
                power_per_minute = pile.power / 60  # 每分钟充电量
                charged_kwh = power_per_minute * charging_minutes
                result["charged_kwh"] = min(charged_kwh, request.amount_kwh)
                
                # 充电进度
                progress = min(charged_kwh / request.amount_kwh * 100, 100) if request.amount_kwh > 0 else 0
                result["charging_progress"] = progress
                result["progress"] = progress
                
                # 预计剩余时间(分钟)
                if charged_kwh < request.amount_kwh:
                    remaining_kwh = request.amount_kwh - charged_kwh
                    result["remaining_kwh"] = remaining_kwh
                    remaining_minutes = remaining_kwh / power_per_minute if power_per_minute > 0 else 0
                    result["estimated_remaining_minutes"] = remaining_minutes
                    result["estimated_end_time"] = datetime.now() + timedelta(minutes=remaining_minutes)
                    
                    # 预估费用
                    try:
                        # 简化的费用估算，仅作显示用
                        from backend.app.services.billing import BillingService
                        charge_fee, service_fee, total_fee = BillingService.calculate_charging_cost(
                            db,
                            request.start_time,
                            datetime.now() + timedelta(minutes=remaining_minutes),
                            request.amount_kwh
                        )
                        result["estimated_fee"] = total_fee
                    except Exception as e:
                        logger.error(f"计算预估费用失败: {e}")
                        result["estimated_fee"] = 0
                else:
                    result["remaining_kwh"] = 0
                    result["estimated_remaining_minutes"] = 0
                    result["estimated_end_time"] = datetime.now()
            else:
                logger.warning(f"充电桩不存在: 请求ID={request_id}, 充电桩ID={request.pile_id}")
        
        # 如果已完成，返回充电会话信息
        elif request.status == RequestStatus.FINISHED:
            logger.info(f"处理已完成请求: ID={request_id}")
            # 查询充电会话
            session = db.query(ChargeSession).filter(ChargeSession.request_id == request.id).first()
            if session:
                result["session_id"] = session.id
                result["charged_kwh"] = session.charged_kwh
                result["charging_minutes"] = session.charging_time
                result["charge_fee"] = session.charge_fee
                result["service_fee"] = session.service_fee
                result["total_fee"] = session.total_fee
                result["start_time"] = session.start_time
                result["end_time"] = session.end_time
                result["progress"] = 100
                result["charging_progress"] = 100
                result["remaining_kwh"] = 0
                result["estimated_remaining_minutes"] = 0
                result["estimated_fee"] = session.total_fee
                
                # 查询详单
                bill_detail = db.query(BillDetail).filter(BillDetail.session_id == session.id).first()
                if bill_detail:
                    result["detail_number"] = bill_detail.detail_number
                    result["bill_id"] = bill_detail.bill_id
            else:
                logger.warning(f"充电会话不存在: 请求ID={request_id}")
        elif request.status in [RequestStatus.WAITING, RequestStatus.QUEUING]:
            logger.info(f"处理等待/排队中请求: ID={request_id}, 状态={request.status}")
            # 对于等待或排队中的请求，保持默认值
            pass
        else:
            logger.info(f"处理其他状态请求: ID={request_id}, 状态={request.status}")
        
        logger.debug(f"最终状态结果: {result}")
        return result
    
    @staticmethod
    def simulate_charging_progress(db: Session, request_id: int, progress_percent: float) -> Tuple[bool, str]:
        """
        模拟充电进度
        用于演示和测试，根据给定的进度百分比更新充电状态
        """
        # 查询充电请求
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            return False, "充电请求不存在"
            
        if request.status != RequestStatus.CHARGING:
            return False, f"充电请求状态错误: {request.status}"
            
        # 查询充电桩
        pile = db.query(ChargePile).filter(ChargePile.id == request.pile_id).first()
        if not pile:
            return False, "充电桩不存在"
            
        # 查询或创建充电会话
        session = db.query(ChargeSession).filter(ChargeSession.request_id == request.id).first()
        if not session:
            success, message, session = ChargingService.create_charge_session(db, request.id)
            if not success:
                return False, message
        
        # 计算充电量和充电时间
        progress = min(max(progress_percent, 0), 100) / 100
        charged_kwh = request.amount_kwh * progress
        
        # 计算充电时间(分钟)
        charging_time_hours = charged_kwh / pile.power
        charging_time = int(charging_time_hours * 60)
        
        # 更新充电会话
        success, message = ChargingService.update_charge_session(db, session.id, charged_kwh, charging_time)
        if not success:
            return False, message
            
        # 如果充电完成，结束充电会话
        if progress >= 1.0:
            success, message, _ = ChargingService.finish_charge_session(db, session.id, charged_kwh, charging_time)
            if not success:
                return False, message
            
        return True, f"成功更新充电进度: {progress_percent}%" 