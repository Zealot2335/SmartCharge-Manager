from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import logging

from backend.app.db.models import ChargePile, CarRequest, QueueLog
from backend.app.db.schemas import ChargeMode, PileStatus, RequestStatus
from backend.app.core.config import get_station_config

logger = logging.getLogger(__name__)

class ChargingScheduler:
    """充电调度器，实现核心调度算法"""
    
    @staticmethod
    def generate_queue_number(db: Session, mode: ChargeMode) -> str:
        """
        生成排队号码
        F开头 → 快充；T开头 → 慢充
        号码格式：<mode><顺序号>，顺序号自增
        """
        # 确定前缀
        prefix = "F" if mode == ChargeMode.FAST else "T"
        
        # 查询当前模式下最大的序号
        last_request = (
            db.query(CarRequest)
            .filter(CarRequest.mode == mode)
            .filter(CarRequest.queue_number.like(f"{prefix}%"))
            .order_by(CarRequest.queue_number.desc())
            .first()
        )
        
        # 计算新序号
        if last_request:
            try:
                last_number = int(last_request.queue_number[1:])
                new_number = last_number + 1
            except ValueError:
                new_number = 1
        else:
            new_number = 1
            
        return f"{prefix}{new_number}"
    
    @staticmethod
    def check_waiting_area_capacity(db: Session) -> bool:
        """
        检查等候区容量是否已满
        返回True表示有空位，False表示已满
        """
        config = get_station_config()
        waiting_area_size = config.get("WaitingAreaSize", 6)
        
        # 计算等候区当前车辆数量
        current_waiting_count = (
            db.query(CarRequest)
            .filter(CarRequest.status == RequestStatus.WAITING)
            .count()
        )
        
        return current_waiting_count < waiting_area_size
    
    @staticmethod
    def get_available_piles(db: Session, mode: ChargeMode) -> List[ChargePile]:
        """获取指定模式下可用的充电桩"""
        pile_type = "FAST" if mode == ChargeMode.FAST else "SLOW"
        return (
            db.query(ChargePile)
            .filter(ChargePile.type == pile_type)
            .filter(ChargePile.status.in_([PileStatus.AVAILABLE, PileStatus.BUSY]))
            .all()
        )
    
    @staticmethod
    def count_waiting_cars(db: Session, mode: ChargeMode) -> int:
        """获取指定模式下等候区等待的车辆数量"""
        return (
            db.query(CarRequest)
            .filter(CarRequest.mode == mode)
            .filter(CarRequest.status == RequestStatus.WAITING)
            .count()
        )
    
    @staticmethod
    def get_pile_queue_length(db: Session, pile_id: int) -> int:
        """获取指定充电桩的当前队列长度"""
        return (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status.in_([RequestStatus.QUEUING, RequestStatus.CHARGING]))
            .count()
        )
    
    @staticmethod
    def check_pile_queue_available(db: Session, pile_id: int) -> bool:
        """检查充电桩队列是否有空位"""
        config = get_station_config()
        queue_len = config.get("ChargingQueueLen", 2)
        
        current_queue_length = ChargingScheduler.get_pile_queue_length(db, pile_id)
        return current_queue_length < queue_len
    
    @staticmethod
    def get_pile_queue_waiting_time(db: Session, pile_id: int) -> float:
        """
        计算指定充电桩的队列等待时间(分钟)
        """
        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if not pile:
            return float('inf')  # 找不到充电桩，返回无穷大
            
        # 获取充电桩功率 (kWh/h)
        power = pile.power
        
        # 查询排队中的请求
        queuing_requests = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status.in_([RequestStatus.QUEUING, RequestStatus.CHARGING]))
            .order_by(CarRequest.queue_position)
            .all()
        )
        
        # 计算总等待时间(分钟)
        total_waiting_time = 0.0
        for request in queuing_requests:
            # 充电时间(小时) = 请求充电量 / 充电功率
            charging_time_hours = request.amount_kwh / power
            # 转换为分钟
            charging_time_minutes = charging_time_hours * 60
            total_waiting_time += charging_time_minutes
            
        return total_waiting_time
    
    @staticmethod
    def calculate_finish_time(db: Session, pile_id: int, amount_kwh: float) -> float:
        """
        计算完成充电所需时长(分钟)
        等待时间 + 自身充电时间
        """
        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if not pile:
            return float('inf')
            
        # 等待时间
        waiting_time = ChargingScheduler.get_pile_queue_waiting_time(db, pile_id)
        
        # 自身充电时间(小时) = 请求充电量 / 充电功率
        self_charging_time_hours = amount_kwh / pile.power
        # 转换为分钟
        self_charging_time_minutes = self_charging_time_hours * 60
        
        return waiting_time + self_charging_time_minutes
    
    @staticmethod
    def select_optimal_pile(db: Session, request_id: int) -> Optional[int]:
        """
        根据调度策略选择最优的充电桩
        策略：完成充电所需时长（等待时间+自己充电时间）最短
        """
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            return None
            
        # 获取可用的充电桩
        available_piles = ChargingScheduler.get_available_piles(db, request.mode)
        if not available_piles:
            return None
            
        best_pile_id = None
        min_finish_time = float('inf')
        
        # 选择完成时间最短的充电桩
        for pile in available_piles:
            # 检查队列是否有空位
            if not ChargingScheduler.check_pile_queue_available(db, pile.id):
                continue
                
            finish_time = ChargingScheduler.calculate_finish_time(db, pile.id, request.amount_kwh)
            if finish_time < min_finish_time:
                min_finish_time = finish_time
                best_pile_id = pile.id
                
        return best_pile_id
    
    @staticmethod
    def assign_to_pile(db: Session, request_id: int, pile_id: int) -> Tuple[bool, str]:
        """
        将请求分配到充电桩队列
        """
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            return False, "充电请求不存在"
            
        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if not pile:
            return False, "充电桩不存在"
            
        # 检查充电桩类型是否匹配
        if (request.mode == ChargeMode.FAST and pile.type != "FAST") or \
           (request.mode == ChargeMode.SLOW and pile.type != "SLOW"):
            return False, "充电桩类型与请求不匹配"
            
        # 检查充电桩队列是否有空位
        if not ChargingScheduler.check_pile_queue_available(db, pile_id):
            return False, "充电桩队列已满"
            
        # 获取队列位置
        queue_position = ChargingScheduler.get_pile_queue_length(db, pile_id)
        
        # 修改请求状态
        old_status = request.status
        request.status = RequestStatus.QUEUING
        request.pile_id = pile_id
        request.queue_position = queue_position
        
        # 创建队列日志
        queue_log = QueueLog(
            request_id=request.id,
            from_status=old_status,
            to_status=RequestStatus.QUEUING,
            pile_id=pile_id,
            queue_position=queue_position,
            remark=f"分配到充电桩 {pile.code}, 队列位置 {queue_position}"
        )
        db.add(queue_log)
        
        # 更新充电桩状态
        if pile.status == PileStatus.AVAILABLE:
            pile.status = PileStatus.BUSY
            
        db.commit()
        return True, f"成功分配到充电桩 {pile.code}, 队列位置 {queue_position}"
    
    @staticmethod
    def call_next_waiting_car(db: Session, mode: ChargeMode) -> Optional[int]:
        """
        调用等候区下一辆车进入充电区
        返回被调度的请求ID，如果没有可调度的车辆则返回None
        """
        # 获取指定模式下，按照排队号码排序的第一辆等待中的车
        next_car = (
            db.query(CarRequest)
            .filter(CarRequest.mode == mode)
            .filter(CarRequest.status == RequestStatus.WAITING)
            .order_by(CarRequest.queue_number)
            .first()
        )
        
        if not next_car:
            return None
            
        # 选择最优的充电桩
        best_pile_id = ChargingScheduler.select_optimal_pile(db, next_car.id)
        if not best_pile_id:
            return None
            
        # 分配到充电桩
        success, _ = ChargingScheduler.assign_to_pile(db, next_car.id, best_pile_id)
        if success:
            return next_car.id
        else:
            return None
    
    @staticmethod
    def check_and_call_waiting_cars(db: Session) -> List[int]:
        """
        检查并调用等候区的车辆
        返回被调度的请求ID列表
        """
        scheduled_cars = []
        
        # 检查快充模式
        fast_piles = ChargingScheduler.get_available_piles(db, ChargeMode.FAST)
        for pile in fast_piles:
            if ChargingScheduler.check_pile_queue_available(db, pile.id):
                car_id = ChargingScheduler.call_next_waiting_car(db, ChargeMode.FAST)
                if car_id:
                    scheduled_cars.append(car_id)
        
        # 检查慢充模式
        slow_piles = ChargingScheduler.get_available_piles(db, ChargeMode.SLOW)
        for pile in slow_piles:
            if ChargingScheduler.check_pile_queue_available(db, pile.id):
                car_id = ChargingScheduler.call_next_waiting_car(db, ChargeMode.SLOW)
                if car_id:
                    scheduled_cars.append(car_id)
                    
        return scheduled_cars
    
    @staticmethod
    def start_charging(db: Session, request_id: int) -> Tuple[bool, str]:
        """
        开始充电，将队列中第一个位置的车辆状态改为充电中
        """
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            return False, "充电请求不存在"
            
        if request.status != RequestStatus.QUEUING:
            return False, f"充电请求状态错误: {request.status}"
            
        if request.queue_position != 0:
            return False, f"队列位置错误，不是第一个位置: {request.queue_position}"
            
        # 修改请求状态
        old_status = request.status
        request.status = RequestStatus.CHARGING
        request.start_time = datetime.now()
        
        # 创建队列日志
        queue_log = QueueLog(
            request_id=request.id,
            from_status=old_status,
            to_status=RequestStatus.CHARGING,
            pile_id=request.pile_id,
            queue_position=request.queue_position,
            remark="开始充电"
        )
        db.add(queue_log)
        db.commit()
        
        return True, "成功开始充电"
    
    @staticmethod
    def finish_charging(db: Session, request_id: int) -> Tuple[bool, str]:
        """
        完成充电，将充电中的车辆状态改为已完成
        """
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            return False, "充电请求不存在"
            
        if request.status != RequestStatus.CHARGING:
            return False, f"充电请求状态错误: {request.status}"
            
        pile_id = request.pile_id
        
        # 修改请求状态
        old_status = request.status
        request.status = RequestStatus.FINISHED
        request.end_time = datetime.now()
        
        # 创建队列日志
        queue_log = QueueLog(
            request_id=request.id,
            from_status=old_status,
            to_status=RequestStatus.FINISHED,
            pile_id=request.pile_id,
            queue_position=request.queue_position,
            remark="完成充电"
        )
        db.add(queue_log)
        
        # 更新队列中其他车辆的位置
        other_cars = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status == RequestStatus.QUEUING)
            .filter(CarRequest.id != request_id)
            .all()
        )
        
        for car in other_cars:
            car.queue_position -= 1
        
        db.commit()
        
        # 检查队列中第一个位置的车辆，将其状态改为充电中
        next_car = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status == RequestStatus.QUEUING)
            .filter(CarRequest.queue_position == 0)
            .first()
        )
        
        if next_car:
            ChargingScheduler.start_charging(db, next_car.id)
            
        # 检查充电桩是否空闲
        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if pile:
            charging_count = (
                db.query(CarRequest)
                .filter(CarRequest.pile_id == pile_id)
                .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
                .count()
            )
            
            if charging_count == 0:
                pile.status = PileStatus.AVAILABLE
                db.commit()
        
        # 检查等候区是否有车可以调度
        ChargingScheduler.check_and_call_waiting_cars(db)
        
        return True, "成功完成充电"
    
    @staticmethod
    def cancel_charging(db: Session, request_id: int) -> Tuple[bool, str]:
        """
        取消充电请求
        """
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            return False, "充电请求不存在"
            
        old_status = request.status
        old_pile_id = request.pile_id
        old_queue_position = request.queue_position
        
        # 修改请求状态
        request.status = RequestStatus.CANCELED
        
        # 创建队列日志
        queue_log = QueueLog(
            request_id=request.id,
            from_status=old_status,
            to_status=RequestStatus.CANCELED,
            pile_id=old_pile_id,
            queue_position=old_queue_position,
            remark="取消充电请求"
        )
        db.add(queue_log)
        
        # 如果是在等候区，直接提交
        if old_status == RequestStatus.WAITING:
            db.commit()
            return True, "成功取消等候区充电请求"
            
        # 如果是在充电区队列中
        if old_status in [RequestStatus.QUEUING, RequestStatus.CHARGING]:
            # 更新队列中其他车辆的位置
            other_cars = (
                db.query(CarRequest)
                .filter(CarRequest.pile_id == old_pile_id)
                .filter(CarRequest.status.in_([RequestStatus.QUEUING, RequestStatus.CHARGING]))
                .filter(CarRequest.id != request_id)
                .all()
            )
            
            for car in other_cars:
                if car.queue_position > old_queue_position:
                    car.queue_position -= 1
            
            db.commit()
            
            # 如果是正在充电的车辆，需要启动队列中下一辆车
            if old_status == RequestStatus.CHARGING:
                next_car = (
                    db.query(CarRequest)
                    .filter(CarRequest.pile_id == old_pile_id)
                    .filter(CarRequest.status == RequestStatus.QUEUING)
                    .filter(CarRequest.queue_position == 0)
                    .first()
                )
                
                if next_car:
                    ChargingScheduler.start_charging(db, next_car.id)
            
            # 检查充电桩是否空闲
            pile = db.query(ChargePile).filter(ChargePile.id == old_pile_id).first()
            if pile:
                charging_count = (
                    db.query(CarRequest)
                    .filter(CarRequest.pile_id == old_pile_id)
                    .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
                    .count()
                )
                
                if charging_count == 0:
                    pile.status = PileStatus.AVAILABLE
                    db.commit()
            
            # 检查等候区是否有车可以调度
            ChargingScheduler.check_and_call_waiting_cars(db)
            
            return True, "成功取消充电区充电请求"
        
        return False, f"无法取消状态为 {old_status} 的充电请求" 