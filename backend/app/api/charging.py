from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from backend.app.db.database import get_db
from backend.app.db.models import User, CarRequest, ChargePile
from backend.app.db.schemas import (
    ChargeRequestCreate, ChargeRequestUpdate, ChargeRequest, 
    ChargeRequestDetail, ChargeMode, RequestStatus
)
from backend.app.core.auth import get_current_user
from backend.app.services.scheduler import ChargingScheduler
from backend.app.services.billing import BillingService
from backend.app.services.charging_service import ChargingService

router = APIRouter()

@router.post("/request", response_model=ChargeRequest)
async def create_charge_request(
    request: ChargeRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """提交充电请求"""
    # 检查等候区是否已满
    if not ChargingScheduler.check_waiting_area_capacity(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="等候区已满，请稍后再试"
        )
    
    # 生成排队号码
    queue_number = ChargingScheduler.generate_queue_number(db, request.mode)
    
    # 创建充电请求
    db_request = CarRequest(
        user_id=current_user.user_id,
        queue_number=queue_number,
        mode=request.mode,
        amount_kwh=request.amount_kwh,
        battery_capacity=request.battery_capacity,
        status=RequestStatus.WAITING,
        request_time=datetime.now()
    )
    
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    
    # 尝试立即调度
    ChargingScheduler.check_and_call_waiting_cars(db)
    
    return db_request

@router.get("/requests", response_model=List[ChargeRequest])
async def get_user_requests(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取用户的充电请求列表"""
    query = db.query(CarRequest).filter(CarRequest.user_id == current_user.user_id)
    
    if status:
        query = query.filter(CarRequest.status == status)
    
    requests = query.order_by(CarRequest.request_time.desc()).all()
    return requests

@router.get("/{request_id}", response_model=ChargeRequestDetail)
async def get_charge_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取充电请求详情"""
    # 查询请求
    request = db.query(CarRequest).filter(
        CarRequest.id == request_id,
        CarRequest.user_id == current_user.user_id
    ).first()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="充电请求不存在"
        )
    
    # 创建响应数据
    result = ChargeRequestDetail.from_orm(request)
    
    # 计算等待人数
    if request.status == RequestStatus.WAITING:
        # 计算同模式下在等候区等待的车辆数量（排在前面的）
        wait_count = (
            db.query(CarRequest)
            .filter(CarRequest.mode == request.mode)
            .filter(CarRequest.status == RequestStatus.WAITING)
            .filter(CarRequest.queue_number < request.queue_number)
            .count()
        )
        result.wait_count = wait_count
        
        # 估算等待时间
        # 简单估计：假设所有充电桩都有车，新来的车需要等待最后一个位置
        pile_count = len(ChargingScheduler.get_available_piles(db, request.mode))
        if pile_count > 0:
            # 假设每辆车平均充电时间为 amount_kwh / power
            power = 30.0 if request.mode == ChargeMode.FAST else 7.0
            avg_charging_time = request.amount_kwh / power * 60  # 转换为分钟
            
            # 估计等待时间 = 前面等待的车辆数 / 充电桩数 * 平均充电时间
            result.estimated_wait_time = (wait_count / pile_count) * avg_charging_time
            
            # 估计完成时间
            if result.estimated_wait_time:
                result.estimated_finish_time = datetime.now() + timedelta(minutes=result.estimated_wait_time)
    
    elif request.status in [RequestStatus.QUEUING, RequestStatus.CHARGING]:
        if request.pile_id:
            # 计算在该充电桩排队的预计等待时间
            waiting_time = ChargingScheduler.get_pile_queue_waiting_time(db, request.pile_id)
            
            # 如果是正在充电的车辆，等待时间为0
            if request.status == RequestStatus.CHARGING:
                result.wait_count = 0
                result.estimated_wait_time = 0
                
                # 计算自身充电时间
                power = db.query(ChargePile).filter(ChargePile.id == request.pile_id).first().power
                charging_time = request.amount_kwh / power * 60  # 转换为分钟
                
                # 估计完成时间
                start_time = request.start_time or datetime.now()
                result.estimated_finish_time = start_time + timedelta(minutes=charging_time)
            else:
                # 排队中的车辆
                # 计算前面排队的车辆数
                result.wait_count = (
                    db.query(CarRequest)
                    .filter(CarRequest.pile_id == request.pile_id)
                    .filter(CarRequest.queue_position < request.queue_position)
                    .count()
                )
                
                # 计算自身充电时间
                power = db.query(ChargePile).filter(ChargePile.id == request.pile_id).first().power
                charging_time = request.amount_kwh / power * 60  # 转换为分钟
                
                # 估计等待时间 = 队列等待时间 - 自身充电时间
                result.estimated_wait_time = waiting_time - charging_time
                
                # 估计完成时间
                result.estimated_finish_time = datetime.now() + timedelta(minutes=waiting_time)
    
    return result

@router.patch("/{request_id}", response_model=ChargeRequest)
async def update_charge_request(
    request_id: int,
    request_update: ChargeRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """修改充电请求"""
    # 查询请求
    request = db.query(CarRequest).filter(
        CarRequest.id == request_id,
        CarRequest.user_id == current_user.user_id
    ).first()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="充电请求不存在"
        )
    
    # 检查请求状态
    if request.status not in [RequestStatus.WAITING, RequestStatus.QUEUING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法修改状态为 {request.status} 的充电请求"
        )
    
    # 修改充电模式
    if request_update.mode is not None and request_update.mode != request.mode:
        # 只允许在等候区修改充电模式
        if request.status != RequestStatus.WAITING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只能在等候区修改充电模式"
            )
        
        # 更新模式和排队号码
        old_mode = request.mode
        request.mode = request_update.mode
        
        # 生成新的排队号码
        request.queue_number = ChargingScheduler.generate_queue_number(db, request.mode)
    
    # 修改充电量
    if request_update.amount_kwh is not None:
        # 充电区只允许取消，不允许修改
        if request.status != RequestStatus.WAITING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只能在等候区修改充电量"
            )
        
        request.amount_kwh = request_update.amount_kwh
    
    db.commit()
    db.refresh(request)
    
    return request

@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_charge_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """取消充电请求"""
    # 查询请求
    request = db.query(CarRequest).filter(
        CarRequest.id == request_id,
        CarRequest.user_id == current_user.user_id
    ).first()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="充电请求不存在"
        )
    
    # 检查请求状态
    if request.status == RequestStatus.FINISHED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已完成的充电请求无法取消"
        )
    
    if request.status == RequestStatus.CANCELED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该充电请求已经取消"
        )
    
    # 取消充电请求
    success, message = ChargingScheduler.cancel_charging(db, request_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

@router.get("/{request_id}/state", response_model=Dict[str, Any])
async def get_charge_state(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取充电实时状态"""
    # 查询请求
    request = db.query(CarRequest).filter(
        CarRequest.id == request_id,
        CarRequest.user_id == current_user.user_id
    ).first()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="充电请求不存在"
        )
    
    # 使用充电服务获取充电状态
    state = ChargingService.get_charging_status(db, request_id)
    
    return state

@router.get("/queue/{mode}", response_model=Dict[str, Any])
async def get_queue_info(
    mode: ChargeMode,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取队列信息"""
    # 查询等候区中该模式的车辆数量
    waiting_count = ChargingScheduler.count_waiting_cars(db, mode)
    
    # 查询充电区中该模式的车辆数量
    piles = ChargingScheduler.get_available_piles(db, mode)
    pile_queues = {}
    total_charging = 0
    total_queuing = 0
    
    for pile in piles:
        # 查询该充电桩的队列
        queue = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile.id)
            .filter(CarRequest.status.in_([RequestStatus.CHARGING, RequestStatus.QUEUING]))
            .order_by(CarRequest.queue_position)
            .all()
        )
        
        charging = [q for q in queue if q.status == RequestStatus.CHARGING]
        queuing = [q for q in queue if q.status == RequestStatus.QUEUING]
        
        pile_queues[pile.code] = {
            "total": len(queue),
            "charging": len(charging),
            "queuing": len(queuing)
        }
        
        total_charging += len(charging)
        total_queuing += len(queuing)
    
    return {
        "mode": mode,
        "waiting_count": waiting_count,
        "charging_count": total_charging,
        "queuing_count": total_queuing,
        "total_count": waiting_count + total_charging + total_queuing,
        "pile_queues": pile_queues
    }

@router.post("/{request_id}/simulate", response_model=Dict[str, Any])
async def simulate_charging(
    request_id: int,
    progress: float = Query(..., ge=0, le=100, description="充电进度百分比(0-100)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    模拟充电进度（仅用于测试）
    """
    # 检查用户权限（只允许管理员或请求的所有者）
    request = db.query(CarRequest).filter(CarRequest.id == request_id).first()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="充电请求不存在"
        )
    
    if request.user_id != current_user.user_id and current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有权限执行此操作"
        )
    
    # 模拟充电进度
    success, message = ChargingService.simulate_charging_progress(db, request_id, progress)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    # 获取最新状态
    state = ChargingService.get_charging_status(db, request_id)
    return {
        "message": message,
        "state": state
    } 