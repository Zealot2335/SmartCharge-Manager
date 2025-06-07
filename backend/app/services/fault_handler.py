from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from backend.app.db.models import ChargePile, CarRequest, FaultLog, QueueLog
from backend.app.db.schemas import ChargeMode, PileStatus, RequestStatus
from backend.app.services.scheduler import ChargingScheduler

logger = logging.getLogger(__name__)

class FaultHandler:
    """故障处理器，实现故障调度策略"""
    
    @staticmethod
    def report_pile_fault(
        db: Session, pile_id: int, description: str = "充电桩故障"
    ) -> Tuple[bool, str]:
        """
        报告充电桩故障
        """
        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if not pile:
            return False, "充电桩不存在"
            
        # 记录故障日志
        fault_log = FaultLog(
            pile_id=pile_id,
            fault_time=datetime.now(),
            description=description,
            status="ACTIVE"
        )
        db.add(fault_log)
        
        # 更新充电桩状态
        pile.status = PileStatus.FAULT
        db.commit()
        
        # 处理正在使用该充电桩的请求
        charging_request = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status == RequestStatus.CHARGING)
            .first()
        )
        
        if charging_request:
            # 中断充电，生成详单
            charging_request.end_time = datetime.now()
            
            # 记录状态变更日志
            queue_log = QueueLog(
                request_id=charging_request.id,
                from_status=RequestStatus.CHARGING,
                to_status=RequestStatus.QUEUING,
                pile_id=pile_id,
                queue_position=0,
                remark="充电桩故障，中断充电"
            )
            db.add(queue_log)
            db.commit()
            
        # 获取故障充电桩的队列中的所有车辆
        queue_cars = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
            .all()
        )
        
        return True, f"充电桩 {pile.code} 故障已报告，影响 {len(queue_cars)} 辆车"
    
    @staticmethod
    def recover_pile_fault(db: Session, pile_id: int) -> Tuple[bool, str]:
        """
        恢复充电桩故障
        """
        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if not pile:
            return False, "充电桩不存在"
            
        # 更新故障日志
        active_fault = (
            db.query(FaultLog)
            .filter(FaultLog.pile_id == pile_id)
            .filter(FaultLog.status == "ACTIVE")
            .order_by(FaultLog.fault_time.desc())
            .first()
        )
        
        if active_fault:
            active_fault.recovery_time = datetime.now()
            active_fault.status = "RESOLVED"
            
        # 更新充电桩状态
        pile.status = PileStatus.AVAILABLE
        db.commit()
        
        return True, f"充电桩 {pile.code} 故障已恢复"
    
    @staticmethod
    def priority_reschedule(db: Session, fault_pile_id: int) -> List[int]:
        """
        优先级调度：
        暂停等候区叫号服务，当其它同类型充电桩队列有空位时，优先为故障充电桩等候队列提供调度，
        待该故障队列中全部车辆调度完毕后，再重新开启等候区叫号服务。
        """
        rescheduled_cars = []
        
        # 获取故障充电桩信息
        fault_pile = db.query(ChargePile).filter(ChargePile.id == fault_pile_id).first()
        if not fault_pile:
            return rescheduled_cars
            
        # 获取故障充电桩的队列中的所有车辆
        queue_cars = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == fault_pile_id)
            .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
            .order_by(CarRequest.queue_position)
            .all()
        )
        
        # 获取同类型的其他充电桩
        same_type_piles = (
            db.query(ChargePile)
            .filter(ChargePile.type == fault_pile.type)
            .filter(ChargePile.id != fault_pile_id)
            .filter(ChargePile.status.in_([PileStatus.AVAILABLE, PileStatus.BUSY]))
            .all()
        )
        
        # 依次为故障队列中的车辆重新调度
        for car in queue_cars:
            best_pile_id = None
            min_finish_time = float('inf')
            
            # 找到最优的充电桩
            for pile in same_type_piles:
                # 检查队列是否有空位
                if not ChargingScheduler.check_pile_queue_available(db, pile.id):
                    continue
                    
                finish_time = ChargingScheduler.calculate_finish_time(db, pile.id, car.amount_kwh)
                if finish_time < min_finish_time:
                    min_finish_time = finish_time
                    best_pile_id = pile.id
            
            if best_pile_id:
                # 记录原状态
                old_status = car.status
                old_pile_id = car.pile_id
                old_queue_position = car.queue_position
                
                # 分配到新的充电桩
                car.pile_id = best_pile_id
                car.status = RequestStatus.QUEUING
                car.queue_position = ChargingScheduler.get_pile_queue_length(db, best_pile_id)
                
                # 记录状态变更日志
                queue_log = QueueLog(
                    request_id=car.id,
                    from_status=old_status,
                    to_status=RequestStatus.QUEUING,
                    pile_id=best_pile_id,
                    queue_position=car.queue_position,
                    remark=f"故障调度：从充电桩 {fault_pile.code} 转移到充电桩 {pile.code}"
                )
                db.add(queue_log)
                
                rescheduled_cars.append(car.id)
                
                # 如果是第一个位置，则启动充电
                if car.queue_position == 0:
                    car.status = RequestStatus.CHARGING
                    car.start_time = datetime.now()
                
                # 更新目标充电桩状态
                pile = db.query(ChargePile).filter(ChargePile.id == best_pile_id).first()
                if pile and pile.status == PileStatus.AVAILABLE:
                    pile.status = PileStatus.BUSY
                
                db.commit()
        
        return rescheduled_cars
    
    @staticmethod
    def time_order_reschedule(db: Session, fault_pile_id: int) -> List[int]:
        """
        时间顺序调度：
        暂停等候区叫号服务，将其它同类型充电桩中尚未充电的车辆与故障候队列中车辆合为一组，
        按照排队号码先后顺序重新调度。调度完毕后，再重新开启等候区叫号服务。
        """
        rescheduled_cars = []
        
        # 获取故障充电桩信息
        fault_pile = db.query(ChargePile).filter(ChargePile.id == fault_pile_id).first()
        if not fault_pile:
            return rescheduled_cars
            
        # 获取故障充电桩的队列中的所有车辆
        fault_queue_cars = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == fault_pile_id)
            .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
            .all()
        )
        
        # 获取同类型的其他充电桩中尚未充电的车辆
        other_queue_cars = (
            db.query(CarRequest)
            .join(ChargePile, CarRequest.pile_id == ChargePile.id)
            .filter(ChargePile.type == fault_pile.type)
            .filter(ChargePile.id != fault_pile_id)
            .filter(CarRequest.status == RequestStatus.QUEUING)
            .all()
        )
        
        # 合并队列
        combined_queue = fault_queue_cars + other_queue_cars
        
        # 按照排队号码排序
        combined_queue.sort(key=lambda x: x.queue_number)
        
        # 获取同类型的所有可用充电桩
        available_piles = (
            db.query(ChargePile)
            .filter(ChargePile.type == fault_pile.type)
            .filter(ChargePile.id != fault_pile_id)
            .filter(ChargePile.status.in_([PileStatus.AVAILABLE, PileStatus.BUSY]))
            .all()
        )
        
        # 清空所有充电桩的队列
        for car in other_queue_cars:
            # 记录原状态
            old_status = car.status
            old_pile_id = car.pile_id
            old_queue_position = car.queue_position
            
            # 临时设置为等待状态
            car.status = RequestStatus.WAITING
            car.pile_id = None
            car.queue_position = None
            
            # 记录状态变更日志
            queue_log = QueueLog(
                request_id=car.id,
                from_status=old_status,
                to_status=RequestStatus.WAITING,
                pile_id=old_pile_id,
                queue_position=old_queue_position,
                remark="故障时间顺序调度：临时移出队列"
            )
            db.add(queue_log)
        
        # 对故障队列车辆也设置为等待状态
        for car in fault_queue_cars:
            # 记录原状态
            old_status = car.status
            old_pile_id = car.pile_id
            old_queue_position = car.queue_position
            
            # 临时设置为等待状态
            car.status = RequestStatus.WAITING
            car.pile_id = None
            car.queue_position = None
            
            # 记录状态变更日志
            queue_log = QueueLog(
                request_id=car.id,
                from_status=old_status,
                to_status=RequestStatus.WAITING,
                pile_id=old_pile_id,
                queue_position=old_queue_position,
                remark="故障时间顺序调度：临时移出队列"
            )
            db.add(queue_log)
        
        db.commit()
        
        # 按照排队号码顺序重新调度
        for car in combined_queue:
            best_pile_id = None
            min_finish_time = float('inf')
            
            # 找到最优的充电桩
            for pile in available_piles:
                # 检查队列是否有空位
                if not ChargingScheduler.check_pile_queue_available(db, pile.id):
                    continue
                    
                finish_time = ChargingScheduler.calculate_finish_time(db, pile.id, car.amount_kwh)
                if finish_time < min_finish_time:
                    min_finish_time = finish_time
                    best_pile_id = pile.id
            
            if best_pile_id:
                # 分配到新的充电桩
                car.pile_id = best_pile_id
                car.status = RequestStatus.QUEUING
                car.queue_position = ChargingScheduler.get_pile_queue_length(db, best_pile_id)
                
                # 记录状态变更日志
                queue_log = QueueLog(
                    request_id=car.id,
                    from_status=RequestStatus.WAITING,
                    to_status=RequestStatus.QUEUING,
                    pile_id=best_pile_id,
                    queue_position=car.queue_position,
                    remark=f"故障时间顺序调度：分配到充电桩 {pile.code}"
                )
                db.add(queue_log)
                
                rescheduled_cars.append(car.id)
                
                # 如果是第一个位置，则启动充电
                if car.queue_position == 0:
                    car.status = RequestStatus.CHARGING
                    car.start_time = datetime.now()
                
                # 更新目标充电桩状态
                pile = db.query(ChargePile).filter(ChargePile.id == best_pile_id).first()
                if pile and pile.status == PileStatus.AVAILABLE:
                    pile.status = PileStatus.BUSY
                
                db.commit()
        
        return rescheduled_cars 