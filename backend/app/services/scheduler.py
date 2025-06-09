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
            .order_by(CarRequest.id.desc())
            .first()
        )
        
        # 计算新序号
        if last_request and last_request.queue_number.startswith(prefix):
            try:
                last_number = int(last_request.queue_number[1:])
                new_number = last_number + 1
            except (ValueError, IndexError):
                # 如果最新的号码格式不正确，则重新从1开始
                count = db.query(CarRequest).filter(CarRequest.mode == mode).count()
                new_number = count + 1
        else:
            count = db.query(CarRequest).filter(CarRequest.mode == mode).count()
            new_number = count + 1
            
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
    def get_available_piles_for_dispatch(db: Session, mode: ChargeMode) -> List[ChargePile]:
        """获取指定模式下可用于调度的充电桩 (状态为可用或繁忙，且队列未满)"""
        pile_type = "FAST" if mode == ChargeMode.FAST else "SLOW"
        all_piles = db.query(ChargePile).filter(
            ChargePile.type == pile_type,
            ChargePile.status.in_([PileStatus.AVAILABLE, PileStatus.BUSY])
        ).all()

        available_piles = []
        for pile in all_piles:
            if ChargingScheduler.check_pile_queue_available(db, pile.id):
                available_piles.append(pile)
        return available_piles

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
        """获取指定充电桩的当前队列长度（仅包括排队的）"""
        return (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status == RequestStatus.QUEUING)
            .count()
        )
    
    @staticmethod
    def check_pile_queue_available(db: Session, pile_id: int) -> bool:
        """检查充电桩队列是否有空位"""
        config = get_station_config()
        queue_len = config.get("ChargingQueueLen", 2)
        
        # 计算充电桩当前队列长度（包括充电中和排队中的车辆）
        current_queue_length = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile_id)
            .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
            .count()
        )
        
        return current_queue_length < queue_len
    
    @staticmethod
    def get_pile_queue_waiting_time(db: Session, pile_id: int, queue_position: Optional[int] = None) -> float:
        """
        计算指定充电桩队列的总预计等待时间(分钟)
        如果提供了queue_position，则只计算位置小于该值的车辆的等待时间
        """
        try:
            logger.info(f"计算充电桩 {pile_id} 的等待时间，队列位置条件: {queue_position}")
            
            pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
            if not pile:
                logger.warning(f"充电桩 {pile_id} 不存在")
                return float('inf')
                
            if pile.power <= 0:
                logger.warning(f"充电桩 {pile_id} 功率为0或负值: {pile.power}")
                return float('inf')

            power = pile.power
            
            query = db.query(CarRequest).filter(
                CarRequest.pile_id == pile_id,
                CarRequest.status.in_([RequestStatus.QUEUING, RequestStatus.CHARGING])
            )
            
            # 如果指定了队列位置，只计算该位置之前的车辆
            if queue_position is not None:
                query = query.filter(CarRequest.queue_position < queue_position)
            
            queuing_requests = query.order_by(CarRequest.queue_position).all()
            logger.info(f"找到 {len(queuing_requests)} 辆队列中的车辆需要计算等待时间")
            
            total_waiting_time = 0.0
            for request in queuing_requests:
                if request.status == RequestStatus.CHARGING and request.start_time:
                    # 正在充电的车辆，计算剩余充电时间
                    duration_hours = (datetime.now() - request.start_time).total_seconds() / 3600
                    charged_kwh = duration_hours * power
                    remaining_kwh = max(0, request.amount_kwh - charged_kwh)
                    remaining_time_hours = remaining_kwh / power
                    total_waiting_time += remaining_time_hours * 60
                    logger.info(f"车辆 {request.id} 正在充电，已充 {charged_kwh:.2f} kWh，剩余 {remaining_kwh:.2f} kWh，剩余时间 {remaining_time_hours*60:.2f} 分钟")
                else:
                    # 排队中的车辆，计算完整充电时间
                    charging_time_hours = request.amount_kwh / power
                    total_waiting_time += charging_time_hours * 60
                    logger.info(f"车辆 {request.id} 在排队中，需要充电 {request.amount_kwh:.2f} kWh，预计需要 {charging_time_hours*60:.2f} 分钟")
            
            logger.info(f"充电桩 {pile_id} 的总等待时间: {total_waiting_time:.2f} 分钟")
            return total_waiting_time
            
        except Exception as e:
            logger.error(f"计算充电桩 {pile_id} 等待时间时发生错误: {e}", exc_info=True)
            return float('inf')
    
    @staticmethod
    def calculate_total_finish_time(db: Session, pile_id: int, amount_kwh: float) -> float:
        """
        计算车辆在该桩的预计总完成时长(分钟) = 等待时间 + 自身充电时间
        """
        pile = db.query(ChargePile).filter(ChargePile.id == pile_id).first()
        if not pile or pile.power <= 0:
            return float('inf')
            
        # 获取当前队列所有车辆的等待时间
        waiting_time = ChargingScheduler.get_pile_queue_waiting_time(db, pile_id)
        self_charging_time_minutes = (amount_kwh / pile.power) * 60
        
        return waiting_time + self_charging_time_minutes
    
    @staticmethod
    def select_optimal_pile(db: Session, request: CarRequest) -> Optional[ChargePile]:
        """
        根据调度策略为指定请求选择最优的充电桩
        策略：完成充电所需时长（等待时间+自己充电时间）最短
        """
        available_piles = ChargingScheduler.get_available_piles_for_dispatch(db, request.mode)
        if not available_piles:
            return None
            
        best_pile = None
        min_finish_time = float('inf')
        
        for pile in available_piles:
            finish_time = ChargingScheduler.calculate_total_finish_time(db, pile.id, request.amount_kwh)
            if finish_time < min_finish_time:
                min_finish_time = finish_time
                best_pile = pile
                
        return best_pile
    
    @staticmethod
    def assign_to_pile(db: Session, request: CarRequest, pile: ChargePile):
        """
        将请求分配到充电桩队列
        """
        try:
            # 获取当前队列中的车辆数量（充电中+排队中）
            current_queue = (
                db.query(CarRequest)
                .filter(CarRequest.pile_id == pile.id)
                .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
                .order_by(CarRequest.queue_position)
                .all()
            )
            
            # 计算新车的队列位置
            queue_position = len(current_queue)
            
            old_status = request.status
            request.status = RequestStatus.QUEUING
            request.pile_id = pile.id
            request.queue_position = queue_position
            
            queue_log = QueueLog(
                request_id=request.id,
                from_status=old_status,
                to_status=RequestStatus.QUEUING,
                pile_id=pile.id,
                queue_position=queue_position,
                remark=f"分配到充电桩 {pile.code}, 队列位置 {queue_position}"
            )
            db.add(queue_log)
            
            if pile.status == PileStatus.AVAILABLE:
                pile.status = PileStatus.BUSY
            
            db.commit()

            logger.info(f"Successfully assigned request {request.id} to pile {pile.code} at position {queue_position}")
            
            if queue_position == 0:
                ChargingScheduler.start_charging(db, request.id)
        except Exception as e:
            logger.error(f"Error assigning request {request.id} to pile {pile.id}: {e}", exc_info=True)
            db.rollback()

    @staticmethod
    def call_next_waiting_car(db: Session, mode: ChargeMode):
        """
        从等候区呼叫下一辆车（如果任何匹配的桩有空位）
        """
        # 1. 检查是否有桩可以接收新车
        logger.info(f"[{mode.value}] Step 1: Getting available piles for dispatch.")
        available_piles = ChargingScheduler.get_available_piles_for_dispatch(db, mode)
        if not available_piles:
            logger.info(f"[{mode.value}] Step 1 Result: No available piles found. Skipping call.")
            return
        logger.info(f"[{mode.value}] Step 1 Result: Found {len(available_piles)} available pile(s): {[p.code for p in available_piles]}")


        # 2. 获取等候区下一辆车 (按排队号FIFO)
        logger.info(f"[{mode.value}] Step 2: Getting next car from waiting area.")
        next_car = db.query(CarRequest).filter(
            CarRequest.mode == mode,
            CarRequest.status == RequestStatus.WAITING
        ).order_by(CarRequest.queue_number).first()
        
        if not next_car:
            logger.info(f"[{mode.value}] Step 2 Result: No waiting cars found.")
            return
        logger.info(f"[{mode.value}] Step 2 Result: Found waiting car with request ID {next_car.id} and queue number {next_car.queue_number}.")
            
        logger.info(f"[{mode.value}] Step 3: Selecting optimal pile for request {next_car.id}.")
        best_pile = ChargingScheduler.select_optimal_pile(db, next_car)
        
        if best_pile:
            logger.info(f"[{mode.value}] Step 3 Result: Optimal pile is {best_pile.code}. Assigning to pile.")
            ChargingScheduler.assign_to_pile(db, next_car, best_pile)
        else:
            logger.warning(f"[{mode.value}] Step 3 Result: No optimal pile found for request {next_car.id}.")

    @staticmethod
    def check_and_call_waiting_cars(db: Session):
        """
        检查并呼叫等候区的车辆 (主调度入口)
        """
        logger.info("--- Main Scheduler: Checking and calling waiting cars ---")
        for mode in [ChargeMode.FAST, ChargeMode.SLOW]:
            ChargingScheduler.call_next_waiting_car(db, mode)
    
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
        
        old_status = request.status
        request.status = RequestStatus.CHARGING
        request.start_time = datetime.now()
        
        # 创建充电会话
        BillingService.create_charge_session(db, request.id, request.pile_id)

        queue_log = QueueLog(
            request_id=request.id, from_status=old_status, to_status=RequestStatus.CHARGING,
            pile_id=request.pile_id, queue_position=request.queue_position, remark="开始充电"
        )
        db.add(queue_log)
        db.commit()
        
        logger.info(f"Request {request.id} has started charging on pile {request.pile_id}.")
        return True, "成功开始充电"
    
    @staticmethod
    def finish_charging(db: Session, request_id: int) -> Tuple[bool, str]:
        """
        完成充电, 并处理后续调度
        """
        logger.info(f"--- Attempting to finish charging for request_id: {request_id} ---")
        with db.begin_nested():
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
                BillingService.complete_charge_session(db, active_session.id)
            else:
                logger.warning(f"Could not find an active charging session for request {request_id} to finalize billing.")

            # 2. 记录日志并释放已完成的请求
            queue_log = QueueLog(
                request_id=request.id, from_status=RequestStatus.CHARGING, to_status=RequestStatus.FINISHED,
                pile_id=pile.id, queue_position=request.queue_position, remark=f"充电完成，从充电桩 {pile.code} 释放"
            )
            db.add(queue_log)
            
            request.status = RequestStatus.FINISHED
            request.end_time = datetime.now()
            request.pile_id = None
            request.queue_position = None
        
        logger.info(f"Request {request_id} has finished and is released. Now managing the queue for pile {pile.code}.")

        # 3. "队内晋升": 处理桩内剩余的排队车辆
        remaining_cars = db.query(CarRequest).filter(CarRequest.pile_id == pile_id).order_by(CarRequest.queue_position).all()
        if remaining_cars:
            logger.info(f"Found {len(remaining_cars)} car(s) remaining in pile {pile.code}'s queue. Updating positions.")
            with db.begin_nested():
                for car in remaining_cars:
                    if car.queue_position is not None and car.queue_position > 0:
                        car.queue_position -= 1
            
            next_car_to_charge = next((car for car in remaining_cars if car.queue_position == 0), None)
            if next_car_to_charge and next_car_to_charge.status == RequestStatus.QUEUING:
                logger.info(f"Promoting request {next_car_to_charge.id} to start charging on pile {pile.code}.")
                ChargingScheduler.start_charging(db, next_car_to_charge.id)

        # 4. 更新充电桩状态
        final_car_count = db.query(CarRequest).filter(CarRequest.pile_id == pile_id).count()
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
                # logger.info("--- Auto-finishing check: No active charging sessions found. ---")
                return

            logger.info(f"--- Auto-finishing check: Found {len(charging_requests)} active charging session(s). Checking each one. ---")
            
            for req in charging_requests:
                if not req.start_time or not req.pile_id:
                    logger.warning(f"--- Auto-finishing check: Skipping request {req.id} due to missing start_time or pile_id. ---")
                    continue

                pile = db.query(ChargePile).filter(ChargePile.id == req.pile_id).first()
                if not pile or pile.power <= 0:
                    logger.warning(f"--- Auto-finishing check: Skipping request {req.id} due to missing pile or pile power is zero. ---")
                    continue

                duration_hours = (datetime.now() - req.start_time).total_seconds() / 3600
                charged_kwh = duration_hours * pile.power
                
                if charged_kwh >= req.amount_kwh:
                    logger.info(f"--- Auto-finishing check: Request {req.id} has reached 100% progress ({charged_kwh:.2f}/{req.amount_kwh:.2f} kWh). Attempting to finish it automatically. ---")
                    ChargingScheduler.finish_charging(db, req.id)
        except Exception as e:
            logger.error(f"--- Auto-finishing check: An unexpected error occurred: {e} ---", exc_info=True)

    @staticmethod
    def cancel_charging(db: Session, request_id: int) -> Tuple[bool, str]:
        """
        取消充电请求
        """
        logger.info(f"--- Attempting to cancel request {request_id} ---")
        request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
        if not request:
            return False, "充电请求不存在"

        if request.status in [RequestStatus.FINISHED, RequestStatus.CANCELED]:
            return False, f"无法取消状态为 {request.status} 的请求"

        old_status = request.status
        old_pile_id = request.pile_id
        
        # 如果是充电中状态，需要结算账单
        if old_status == RequestStatus.CHARGING and old_pile_id:
            active_session = db.query(ChargeSession).filter(
                ChargeSession.request_id == request_id, 
                ChargeSession.status == "CHARGING"
            ).first()
            
            if active_session:
                logger.info(f"Request {request_id} was in CHARGING state. Interrupting charging session {active_session.id}.")
                
                # 计算已充电量
                pile = db.query(ChargePile).filter(ChargePile.id == old_pile_id).first()
                if pile and request.start_time:
                    charging_hours = (datetime.now() - request.start_time).total_seconds() / 3600
                    charged_kwh = min(request.amount_kwh, pile.power * charging_hours)
                    
                    # 中断充电会话并结算
                    BillingService.interrupt_charge_session(db, active_session.id, charged_kwh)
                    logger.info(f"Charging session {active_session.id} interrupted with {charged_kwh:.2f} kWh charged.")
                else:
                    logger.warning(f"Could not calculate charged amount for request {request_id}. Using session interrupt with default calculation.")
                    BillingService.interrupt_charge_session(db, active_session.id)
            else:
                logger.warning(f"Could not find an active charging session for request {request_id}.")

        # 记录取消日志
        queue_log = QueueLog(
            request_id=request.id, from_status=old_status, to_status=RequestStatus.CANCELED,
            remark=f"用户取消请求，原始状态: {old_status}"
        )
        db.add(queue_log)

        # 更新请求状态
        request.status = RequestStatus.CANCELED
        request.pile_id = None
        request.queue_position = None
        request.end_time = datetime.now()

        db.commit()
        logger.info(f"Request {request_id} status set to CANCELED.")

        # 如果取消的是在充电桩队列中的车，需要进行后续处理
        if old_status in [RequestStatus.QUEUING, RequestStatus.CHARGING] and old_pile_id:
            logger.info(f"Request was in pile {old_pile_id}, proceeding to manage queue.")
            # 重新触发一次完成流程，来处理队列晋升和状态更新
            # 这是最安全的方式，因为它会检查队内下一辆车，并检查是否需要从等候区拉人
            ChargingScheduler.finish_charging(db, request.id)
        
        return True, "成功取消充电请求"

    @staticmethod
    def fix_pile_charging_status(db: Session):
        """
        修复充电桩队列数据 - 系统启动时调用
        确保每个充电桩只有位置0的车辆处于CHARGING状态
        """
        logger.info("执行修复充电桩队列数据的操作...")
        try:
            # 获取所有充电桩
            piles = db.query(ChargePile).all()
            for pile in piles:
                # 获取该充电桩的所有排队车辆
                queue_cars = (
                    db.query(CarRequest)
                    .filter(CarRequest.pile_id == pile.id)
                    .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
                    .order_by(CarRequest.queue_position)
                    .all()
                )
                
                # 如果队列为空，确保充电桩状态为AVAILABLE
                if not queue_cars and pile.status == PileStatus.BUSY:
                    pile.status = PileStatus.AVAILABLE
                    logger.info(f"修复: 充电桩 {pile.code} 没有车辆但状态为BUSY，已改为AVAILABLE")
                    continue
                
                # 检查队列中的车辆状态
                for i, car in enumerate(queue_cars):
                    if i == 0 and car.status == RequestStatus.QUEUING:
                        # 第一个位置的车应该在充电
                        car.status = RequestStatus.CHARGING
                        car.start_time = datetime.now()
                        logger.info(f"修复: 将队列位置0的车辆 {car.id} 状态从QUEUING改为CHARGING")
                        
                        # 确保充电桩状态为BUSY
                        if pile.status == PileStatus.AVAILABLE:
                            pile.status = PileStatus.BUSY
                            logger.info(f"修复: 充电桩 {pile.code} 有车辆充电但状态为AVAILABLE，已改为BUSY")
                    
                    elif i > 0 and car.status == RequestStatus.CHARGING:
                        # 非第一个位置的车不应该在充电
                        car.status = RequestStatus.QUEUING
                        car.start_time = None
                        logger.info(f"修复: 将非队列位置0的车辆 {car.id} 状态从CHARGING改为QUEUING")
                    
                    # 确保队列位置正确
                    if car.queue_position != i:
                        logger.info(f"修复: 车辆 {car.id} 队列位置从 {car.queue_position} 改为 {i}")
                        car.queue_position = i
            
            db.commit()
            logger.info("充电桩队列数据修复完成")
        except Exception as e:
            logger.error(f"修复充电桩队列数据失败: {e}", exc_info=True)
            db.rollback()

    @staticmethod
    def get_available_piles(db: Session, mode: ChargeMode) -> List[ChargePile]:
        """获取指定模式下可用的充电桩(状态为可用或繁忙)"""
        pile_type = "FAST" if mode == ChargeMode.FAST else "SLOW"
        return (
            db.query(ChargePile)
            .filter(ChargePile.type == pile_type)
            .filter(ChargePile.status.in_([PileStatus.AVAILABLE, PileStatus.BUSY]))
            .all()
        ) 