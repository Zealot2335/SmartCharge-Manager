from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import logging

from backend.app.db.models import ChargePile, CarRequest, QueueLog, ChargeSession
from backend.app.db.schemas import ChargeMode, PileStatus, RequestStatus
from backend.app.core.config import get_station_config
from backend.app.services.billing import BillingService

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
    def get_all_piles_by_mode(db: Session, mode: ChargeMode) -> List[ChargePile]:
        """获取指定模式下的所有充电桩，无论其状态如何"""
        pile_type = "FAST" if mode == ChargeMode.FAST else "SLOW"
        return (
            db.query(ChargePile)
            .filter(ChargePile.type == pile_type)
            .all()
        )
    
    @staticmethod
    def get_available_piles(db: Session, mode: ChargeMode) -> List[ChargePile]:
        """获取指定模式下可用于调度的充电桩"""
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
        """获取指定充电桩的当前队列长度（包括正在充电和排队的）"""
        return (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
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
    def get_pile_queue_waiting_time(db: Session, pile_id: int, before_position: Optional[int] = None) -> float:
        """
        计算指定充电桩队列在某个位置之前的预计等待时间(分钟)
        :param pile_id: 充电桩ID
        :param before_position: 计算截止到的队列位置(不包含此位置), 如果为None则计算整个队列
        """
        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if not pile or pile.power == 0:
            return 0.0

        power = pile.power
        
        # 查询此位置前排队中的请求
        query = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status.in_([RequestStatus.QUEUING, RequestStatus.CHARGING]))
        )
        
        if before_position is not None:
            query = query.filter(CarRequest.queue_position < before_position)
            
        queuing_requests = query.order_by(CarRequest.queue_position).all()
        
        # 计算总等待时间(分钟)
        total_waiting_time = 0.0
        for request in queuing_requests:
            if request.status == RequestStatus.CHARGING and request.start_time:
                # 正在充电的车辆，计算剩余充电时间
                already_charged_duration = (datetime.now() - request.start_time).total_seconds() / 3600 # hours
                already_charged_kwh = already_charged_duration * power
                remaining_kwh = request.amount_kwh - already_charged_kwh
                if remaining_kwh > 0:
                    remaining_time_hours = remaining_kwh / power
                    total_waiting_time += remaining_time_hours * 60
            else:
                # 排队中的车辆，计算完整充电时间
                charging_time_hours = request.amount_kwh / power
                total_waiting_time += charging_time_hours * 60
            
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
        logger.debug(f"Attempting to assign request {request_id} to pile {pile_id}")
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            logger.error(f"Assign failed: Request {request_id} not found.")
            return False, "充电请求不存在"
        
        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if not pile:
            logger.error(f"Assign failed: Pile {pile_id} not found.")
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
        
        # --- 这里是核心修改 ---
        should_start_charging = (queue_position == 0 and pile.status == PileStatus.AVAILABLE)
        
        # 更新充电桩状态
        if pile.status == PileStatus.AVAILABLE:
            pile.status = PileStatus.BUSY
        
        # 提交分配的事务
        db.commit()

        # 如果需要，独立启动充电流程
        if should_start_charging:
            logger.info(f"Request {request.id} is at the front of the queue for an available pile. Starting charging immediately.")
            # 直接调用 start_charging，它会处理状态变更和日志记录
            success, msg = ChargingScheduler.start_charging(db, request.id)
            if not success:
                logger.error(f"Failed to start charging for request {request.id}: {msg}")
                # 启动失败，需要考虑回滚或错误处理
        # --- 修改结束 ---
        
        logger.info(f"Successfully assigned request {request_id} to pile {pile.code} (ID: {pile_id}) at position {queue_position}")
        return True, f"成功分配到充电桩 {pile.code}, 队列位置 {queue_position}"
    
    @staticmethod
    def call_next_waiting_car(db: Session, mode: ChargeMode) -> Optional[int]:
        """
        调用等候区下一辆车进入充电区
        返回被调度的请求ID，如果没有可调度的车辆则返回None
        """
        logger.debug(f"Calling next waiting car for {mode.value} mode.")
        # 获取指定模式下，按照排队号码排序的第一辆等待中的车
        next_car = (
            db.query(CarRequest)
            .filter(CarRequest.mode == mode)
            .filter(CarRequest.status == RequestStatus.WAITING)
            .order_by(CarRequest.queue_number)
            .first()
        )
        
        if not next_car:
            logger.debug(f"No waiting cars found for {mode.value} mode.")
            return None
            
        # 选择最优的充电桩
        logger.debug(f"Found waiting car: request {next_car.id}. Selecting optimal pile.")
        best_pile_id = ChargingScheduler.select_optimal_pile(db, next_car.id)
        if not best_pile_id:
            logger.debug(f"No optimal pile found for request {next_car.id}.")
            return None
            
        # 分配到充电桩
        logger.info(f"Optimal pile for request {next_car.id} is {best_pile_id}. Assigning to pile.")
        success, _ = ChargingScheduler.assign_to_pile(db, next_car.id, best_pile_id)
        if success:
            logger.info(f"Successfully assigned request {next_car.id} to pile {best_pile_id}.")
            return next_car.id
        else:
            logger.error(f"Failed to assign request {next_car.id} to pile {best_pile_id}.")
            return None
    
    @staticmethod
    def check_and_call_waiting_cars(db: Session) -> List[int]:
        """
        检查并呼叫等候区的车辆
        这是调度的主要入口点
        """
        logger.info("--- Main Scheduler: Checking and calling waiting cars ---")

        # 核心保障：先检查并结束已完成的充电，释放资源
        ChargingScheduler.check_and_finish_completed_charges(db)

        # 获取所有可用充电桩 (快充和慢充)
        fast_piles = ChargingScheduler.get_available_piles(db, ChargeMode.FAST)
        slow_piles = ChargingScheduler.get_available_piles(db, ChargeMode.SLOW)

        scheduled_cars = []
        for mode in [ChargeMode.FAST, ChargeMode.SLOW]:
            while True:
                car_id = ChargingScheduler.call_next_waiting_car(db, mode)
                if car_id:
                    scheduled_cars.append(car_id)
                    logger.info(f"Scheduled car request {car_id} for {mode.value} charging.")
                else:
                    # No more cars can be scheduled for this mode
                    break
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
        完成充电, 并处理后续调度
        """
        logger.info(f"--- Attempting to finish charging for request_id: {request_id} ---")
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            logger.error(f"Finish charging failed: Request {request_id} not found.")
            return False, "充电请求不存在"

        if request.status != RequestStatus.CHARGING:
            logger.warning(f"Finish charging called on a non-charging request. Status: {request.status}")
            return False, f"充电请求状态为 {request.status}，无法完成充电"

        pile_id = request.pile_id
        if not pile_id:
            logger.error(f"FATAL: Request {request_id} is CHARGING but has no pile_id.")
            request.status = RequestStatus.FINISHED
            db.commit()
            return False, "请求状态不一致"

        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if not pile:
            logger.error(f"Finish charging failed: Pile {pile_id} not found for request {request_id}.")
            return False, "充电桩不存在"

        # 1. 结算账单
        active_session = db.query(ChargeSession).filter(ChargeSession.request_id == request_id, ChargeSession.status == "CHARGING").first()
        if active_session:
            session = BillingService.complete_charge_session(db, active_session.id)
            if not session:
                logger.error(f"Billing session for request {request_id} (session {active_session.id}) could not be finalized.")
        else:
            logger.warning(f"Could not find an active charging session for request {request_id} to finalize billing.")

        # 2. 记录日志并释放已完成的请求
        queue_log = QueueLog(
            request_id=request.id,
            from_status=RequestStatus.CHARGING,
            to_status=RequestStatus.FINISHED,
            pile_id=pile.id,
            queue_position=request.queue_position,
            remark=f"充电完成，从充电桩 {pile.code} 释放"
        )
        db.add(queue_log)
        
        request.status = RequestStatus.FINISHED
        request.end_time = datetime.now()
        request.pile_id = None
        request.queue_position = None
        db.commit()
        logger.info(f"Request {request_id} has finished and is released. Now managing the queue for pile {pile.code}.")

        # 3. "队内晋升": 处理桩内剩余的排队车辆
        remaining_cars = db.query(CarRequest).filter(CarRequest.pile_id == pile.id).order_by(CarRequest.queue_position).all()
        if remaining_cars:
            logger.info(f"Found {len(remaining_cars)} car(s) remaining in pile {pile.code}'s queue. Updating positions.")
            for car in remaining_cars:
                if car.queue_position > 0:
                    car.queue_position -= 1
            db.commit()

            next_car_to_charge = db.query(CarRequest).filter(CarRequest.pile_id == pile.id, CarRequest.queue_position == 0).first()
            if next_car_to_charge and next_car_to_charge.status == RequestStatus.QUEUING:
                logger.info(f"Promoting request {next_car_to_charge.id} to start charging on pile {pile.code}.")
                ChargingScheduler.start_charging(db, next_car_to_charge.id)

        # 4. 更新充电桩状态
        final_car_count = db.query(CarRequest).filter(CarRequest.pile_id == pile.id).count()
        if final_car_count == 0:
            pile.status = PileStatus.AVAILABLE
            logger.info(f"Pile {pile.code} status set to AVAILABLE as it is now empty.")
        else:
            pile.status = PileStatus.BUSY
            logger.info(f"Pile {pile.code} remains BUSY with {final_car_count} car(s) in its queue.")
        db.commit()

        # 5. 触发全局调度
        logger.info(f"Pile {pile.code} queue management finished. Now checking main waiting area for new cars to schedule.")
        ChargingScheduler.check_and_call_waiting_cars(db)
        
        return True, "充电完成"
    
    @staticmethod
    def check_and_finish_completed_charges(db: Session):
        """
        检查并结束所有已完成的充电任务
        这是为了防止客户端没有上报完成状态导致调度卡死的核心保障机制
        """
        logger.info("--- Auto-finishing check: Starting scan for completed charges. ---")
        
        try:
            charging_requests = db.query(CarRequest).filter(CarRequest.status == RequestStatus.CHARGING).all()
            
            if not charging_requests:
                logger.info("--- Auto-finishing check: No active charging sessions found. ---")
                return

            logger.info(f"--- Auto-finishing check: Found {len(charging_requests)} active charging session(s). Checking each one. ---")
            
            finished_count = 0
            for req in charging_requests:
                if not req.start_time or not req.pile_id:
                    logger.warning(f"--- Auto-finishing check: Skipping request {req.id} due to missing start_time or pile_id. ---")
                    continue

                pile = db.query(ChargePile).filter(ChargePile.id == req.pile_id).first()
                if not pile or pile.power == 0:
                    logger.warning(f"--- Auto-finishing check: Skipping request {req.id} due to missing pile or pile power is zero. ---")
                    continue

                # 计算进度
                duration_hours = (datetime.now() - req.start_time).total_seconds() / 3600
                charged_kwh = duration_hours * pile.power
                progress = (charged_kwh / req.amount_kwh) * 100 if req.amount_kwh > 0 else 100
                
                logger.info(f"--- Auto-finishing check: Request {req.id} on Pile {pile.code} - Progress: {progress:.2f}% ({charged_kwh:.2f}/{req.amount_kwh:.2f} kWh).")
                
                if progress >= 100:
                    logger.info(f"--- Auto-finishing check: Request {req.id} has reached 100% progress. Attempting to finish it automatically. ---")
                    # 在一个独立的事务中完成充电，以避免会话冲突
                    ChargingScheduler.finish_charging(db, req.id)
                    finished_count += 1
            
            if finished_count > 0:
                logger.info(f"--- Auto-finishing check: Successfully auto-finished {finished_count} completed charge(s). ---")
            else:
                logger.info("--- Auto-finishing check: No charges were ready to be finished in this cycle. ---")

        except Exception as e:
            logger.error(f"--- Auto-finishing check: An unexpected error occurred: {e} ---", exc_info=True)

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
            
            # 核心保障：先检查并结束已完成的充电，释放资源
            ChargingScheduler.check_and_finish_completed_charges(db)
            
            return True, "成功取消充电区充电请求"
        
        return False, f"无法取消状态为 {old_status} 的充电请求" 