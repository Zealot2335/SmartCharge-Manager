from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import date, datetime

from backend.app.db.database import get_db
from backend.app.db.models import User, ChargePile, CarRequest, RateRule, ServiceRate
from backend.app.db.schemas import (
    ChargePile as ChargePileSchema, PileStatus,
    RateRule as RateRuleSchema, RateType, ServiceRate as ServiceRateSchema,
    RequestStatus
)
from backend.app.core.auth import get_admin_user
from backend.app.services.report import ReportService
from backend.app.services.fault_handler import FaultHandler
from backend.app.services.scheduler import ChargingScheduler

router = APIRouter()

@router.get("/pile", response_model=List[Dict[str, Any]])
async def get_all_piles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """获取所有充电桩状态"""
    piles = db.query(ChargePile).order_by(ChargePile.id).all()
    
    result = []
    for pile in piles:
        # 查询该充电桩的队列
        queue = (
            db.query(CarRequest)
            .filter(CarRequest.pile_id == pile.id)
            .filter(CarRequest.status.in_(["CHARGING", "QUEUING"]))
            .order_by(CarRequest.queue_position)
            .all()
        )
        
        # 计算队列数据
        charging_car = None
        queuing_cars = []
        
        for car in queue:
            car_data = {
                "id": car.id,
                "user_id": car.user_id,
                "queue_number": car.queue_number,
                "battery_capacity": car.battery_capacity,
                "amount_kwh": car.amount_kwh,
                "status": car.status,
                "queue_position": car.queue_position,
                "request_time": car.request_time
            }
            
            if car.status == "CHARGING":
                charging_car = car_data
                if car.start_time:
                    charging_car["start_time"] = car.start_time
                    charging_minutes = (datetime.now() - car.start_time).total_seconds() / 60
                    charging_car["charging_minutes"] = charging_minutes
                    
                    # 估算已充电量
                    power_per_minute = pile.power / 60  # 每分钟充电量
                    charged_kwh = power_per_minute * charging_minutes
                    charging_car["charged_kwh"] = min(charged_kwh, car.amount_kwh)
                    charging_car["charging_progress"] = min(charged_kwh / car.amount_kwh * 100, 100)
            else:
                queuing_cars.append(car_data)
        
        # 构建充电桩数据
        pile_data = {
            "id": pile.id,
            "code": pile.code,
            "type": pile.type,
            "status": pile.status,
            "power": pile.power,
            "total_charge_count": pile.total_charge_count,
            "total_charge_time": pile.total_charge_time,
            "total_charge_amount": pile.total_charge_amount,
            "queue_length": len(queue),
            "charging_car": charging_car,
            "queuing_cars": queuing_cars
        }
        
        result.append(pile_data)
    
    return result

@router.get("/pile/{code}", response_model=Dict[str, Any])
async def get_pile_detail(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """获取指定充电桩详情"""
    pile = db.query(ChargePile).filter(ChargePile.code == code).first()
    
    if not pile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到充电桩 {code}"
        )
    
    # 查询该充电桩的队列
    queue = (
        db.query(CarRequest)
        .filter(CarRequest.pile_id == pile.id)
        .filter(CarRequest.status.in_(["CHARGING", "QUEUING"]))
        .order_by(CarRequest.queue_position)
        .all()
    )
    
    # 计算队列数据
    charging_car = None
    queuing_cars = []
    
    for car in queue:
        car_data = {
            "id": car.id,
            "user_id": car.user_id,
            "queue_number": car.queue_number,
            "battery_capacity": car.battery_capacity,
            "amount_kwh": car.amount_kwh,
            "status": car.status,
            "queue_position": car.queue_position,
            "request_time": car.request_time
        }
        
        if car.status == "CHARGING":
            charging_car = car_data
            if car.start_time:
                charging_car["start_time"] = car.start_time
                charging_minutes = (datetime.now() - car.start_time).total_seconds() / 60
                charging_car["charging_minutes"] = charging_minutes
                
                # 估算已充电量
                power_per_minute = pile.power / 60  # 每分钟充电量
                charged_kwh = power_per_minute * charging_minutes
                charging_car["charged_kwh"] = min(charged_kwh, car.amount_kwh)
                charging_car["charging_progress"] = min(charged_kwh / car.amount_kwh * 100, 100)
        else:
            queuing_cars.append(car_data)
    
    # 查询故障记录
    from backend.app.db.models import FaultLog
    fault_logs = (
        db.query(FaultLog)
        .filter(FaultLog.pile_id == pile.id)
        .order_by(FaultLog.fault_time.desc())
        .limit(10)
        .all()
    )
    
    fault_history = []
    for log in fault_logs:
        fault_history.append({
            "id": log.id,
            "fault_time": log.fault_time,
            "recovery_time": log.recovery_time,
            "status": log.status,
            "description": log.description
        })
    
    # 构建充电桩详情
    pile_detail = {
        "id": pile.id,
        "code": pile.code,
        "type": pile.type,
        "status": pile.status,
        "power": pile.power,
        "total_charge_count": pile.total_charge_count,
        "total_charge_time": pile.total_charge_time,
        "total_charge_amount": pile.total_charge_amount,
        "queue_length": len(queue),
        "charging_car": charging_car,
        "queuing_cars": queuing_cars,
        "fault_history": fault_history
    }
    
    return pile_detail

@router.post("/pile/{code}/poweron", response_model=Dict[str, Any])
async def power_on_pile(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """启动充电桩"""
    pile = db.query(ChargePile).filter(ChargePile.code == code).first()
    
    if not pile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到充电桩 {code}"
        )
    
    if pile.status == PileStatus.FAULT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"充电桩 {code} 处于故障状态，无法启动"
        )
    
    if pile.status != PileStatus.OFFLINE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"充电桩 {code} 已经处于运行状态"
        )
    
    # 更新充电桩状态
    pile.status = PileStatus.AVAILABLE
    db.commit()
    
    return {"code": code, "status": pile.status, "message": f"充电桩 {code} 已启动"}

@router.post("/pile/{code}/shutdown", response_model=Dict[str, Any])
async def shutdown_pile(
    code: str,
    strategy: str = Query("priority", description="故障恢复策略，priority或time_order"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """关闭充电桩"""
    pile = db.query(ChargePile).filter(ChargePile.code == code).first()
    
    if not pile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到充电桩 {code}"
        )
    
    if pile.status == PileStatus.OFFLINE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"充电桩 {code} 已经处于关闭状态"
        )
    
    # 检查是否有正在充电的车辆
    charging_car = (
        db.query(CarRequest)
        .filter(CarRequest.pile_id == pile.id)
        .filter(CarRequest.status == "CHARGING")
        .first()
    )
    
    # 如果有正在充电的车辆或排队中的车辆，先处理这些车辆
    affected_cars = 0
    rescheduled_cars = []
    
    try:
        # 先报告故障，这会停止计费并生成详单，将所有车辆移回等候区
        if charging_car or db.query(CarRequest).filter(CarRequest.pile_id == pile.id).filter(CarRequest.status == "QUEUING").count() > 0:
            success, message = FaultHandler.report_pile_fault(db, pile.id, f"管理员禁用充电桩 {code}")
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=message
                )
            
            # 获取所有被移回等候区的车辆
            affected_requests = (
                db.query(CarRequest)
                .filter(CarRequest.status == RequestStatus.WAITING)
                .filter(CarRequest.end_time != None)  # 曾经充过电的
                .all()
            )
            affected_cars = len(affected_requests)
            
            # 重新调度这些车辆
            for request in affected_requests:
                # 根据策略选择调度方法
                if strategy == "priority":
                    # 找到最优的同类型充电桩
                    best_pile = ChargingScheduler.find_best_pile(db, request.mode, request.amount_kwh)
                    if best_pile:
                        # 分配到充电桩
                        success = ChargingScheduler.assign_to_pile(db, request.id, best_pile.id)
                        if success:
                            rescheduled_cars.append(request.id)
                elif strategy == "time_order":
                    # 时间顺序调度，按照排队号码排序
                    # 这里简化处理，直接调用调度器的方法
                    success = ChargingScheduler.schedule_request(db, request.id)
                    if success:
                        rescheduled_cars.append(request.id)
        
        # 更新充电桩状态为关闭
        pile.status = PileStatus.OFFLINE
        db.commit()
        
        if affected_cars > 0:
            return {
                "code": code, 
                "status": PileStatus.OFFLINE, 
                "message": f"充电桩 {code} 已关闭，影响 {affected_cars} 辆车，重新调度 {len(rescheduled_cars)} 辆车",
                "strategy": strategy,
                "affected_cars": affected_cars,
                "rescheduled_cars": len(rescheduled_cars)
            }
        else:
            return {"code": code, "status": PileStatus.OFFLINE, "message": f"充电桩 {code} 已关闭"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"关闭充电桩失败: {str(e)}"
        )

@router.get("/requests", response_model=List[Dict[str, Any]])
async def get_recent_requests(
    limit: int = Query(10, description="返回的请求数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """获取最近的充电请求"""
    requests = (
        db.query(CarRequest)
        .order_by(CarRequest.request_time.desc())
        .limit(limit)
        .all()
    )
    
    result = []
    for req in requests:
        result.append({
            "id": req.id,
            "queue_number": req.queue_number,
            "user_id": req.user_id,
            "mode": req.mode,
            "amount_kwh": req.amount_kwh,
            "status": req.status,
            "pile_code": req.pile.code if req.pile else None,
            "request_time": req.request_time,
        })
    return result

@router.post("/pile/{code}/fault", response_model=Dict[str, Any])
async def report_pile_fault(
    code: str,
    description: str = Query(..., description="故障描述"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """报告充电桩故障"""
    pile = db.query(ChargePile).filter(ChargePile.code == code).first()
    
    if not pile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到充电桩 {code}"
        )
    
    if pile.status == PileStatus.FAULT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"充电桩 {code} 已处于故障状态"
        )
    
    if pile.status == PileStatus.OFFLINE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"充电桩 {code} 处于关闭状态，无法报告故障"
        )
    
    # 报告故障
    success, message = FaultHandler.report_pile_fault(db, pile.id, description)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    return {"code": code, "status": "FAULT", "message": message}

@router.post("/pile/{code}/recover", response_model=Dict[str, Any])
async def recover_pile_fault(
    code: str,
    strategy: str = Query("priority", description="故障恢复策略，priority或time_order"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """恢复充电桩故障"""
    pile = db.query(ChargePile).filter(ChargePile.code == code).first()
    
    if not pile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到充电桩 {code}"
        )
    
    if pile.status != PileStatus.FAULT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"充电桩 {code} 不处于故障状态"
        )
    
    # 恢复故障
    success, message = FaultHandler.recover_pile_fault(db, pile.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    # 重新调度
    if strategy == "priority":
        rescheduled_cars = FaultHandler.priority_reschedule(db, pile.id)
    elif strategy == "time_order":
        rescheduled_cars = FaultHandler.time_order_reschedule(db, pile.id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知的故障恢复策略: {strategy}"
        )
    
    return {
        "code": code, 
        "status": pile.status, 
        "message": message,
        "strategy": strategy,
        "rescheduled_count": len(rescheduled_cars)
    }

@router.get("/rate-rule", response_model=List[RateRuleSchema])
async def get_rate_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """获取费率规则"""
    rules = db.query(RateRule).all()
    return rules

@router.patch("/rate-rule", response_model=Dict[str, Any])
async def update_rate_rule(
    type: RateType,
    price: float = Query(..., gt=0, description="电价(元/kWh)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """更新费率规则"""
    # 更新所有该类型的费率规则
    rules = db.query(RateRule).filter(RateRule.type == type).all()
    
    if not rules:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到 {type} 类型的费率规则"
        )
    
    # 更新费率
    for rule in rules:
        rule.price = price
    
    db.commit()
    
    return {
        "type": type,
        "price": price,
        "message": f"{type} 类型的费率已更新为 {price} 元/kWh",
        "updated_count": len(rules)
    }

@router.get("/service-rate", response_model=ServiceRateSchema)
async def get_service_rate(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """获取当前服务费率"""
    rate = db.query(ServiceRate).filter(ServiceRate.is_current == True).first()
    
    if not rate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到当前服务费率"
        )
    
    return rate

@router.patch("/service-rate", response_model=ServiceRateSchema)
async def update_service_rate(
    rate: float = Query(..., gt=0, description="服务费率(元/kWh)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """更新服务费率"""
    # 将当前费率设置为非当前
    current_rate = db.query(ServiceRate).filter(ServiceRate.is_current == True).all()
    for r in current_rate:
        r.is_current = False
    
    # 创建新费率
    new_rate = ServiceRate(
        rate=rate,
        effective_from=datetime.now(),
        is_current=True
    )
    
    db.add(new_rate)
    db.commit()
    db.refresh(new_rate)
    
    return new_rate

@router.get("/reports/daily/{report_date}", response_model=Dict[str, Any])
async def get_daily_report(
    report_date: date,
    export_csv: bool = Query(False, description="是否导出为CSV格式"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """获取日报表"""
    reports = ReportService.get_daily_report(db, report_date)
    
    if export_csv:
        csv_content = ReportService.export_daily_report_csv(db, report_date)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=daily_report_{report_date}.csv"
            }
        )
    
    # 转换为字典格式
    result = []
    for report in reports:
        result.append({
            "report_date": report.report_date,
            "pile_id": report.pile_id,
            "pile_code": report.pile_code,
            "charge_count": report.charge_count,
            "charge_time": report.charge_time,
            "charge_kwh": report.charge_kwh,
            "charge_fee": report.charge_fee,
            "service_fee": report.service_fee,
            "total_fee": report.total_fee
        })
    
    # 计算总计
    total_charge_count = sum(report.charge_count for report in reports)
    total_charge_time = sum(report.charge_time for report in reports)
    total_charge_kwh = sum(report.charge_kwh for report in reports)
    total_charge_fee = sum(report.charge_fee for report in reports)
    total_service_fee = sum(report.service_fee for report in reports)
    total_fee = sum(report.total_fee for report in reports)
    
    return {
        "report_date": report_date,
        "reports": result,
        "summary": {
            "total_charge_count": total_charge_count,
            "total_charge_time": total_charge_time,
            "total_charge_kwh": total_charge_kwh,
            "total_charge_fee": total_charge_fee,
            "total_service_fee": total_service_fee,
            "total_fee": total_fee
        }
    }

@router.get("/reports/weekly", response_model=Dict[str, Any])
async def get_weekly_report(
    date_in_week: date = Query(..., description="周内任意日期"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """获取周报表"""
    report = ReportService.get_weekly_report(db, date_in_week)
    return report

@router.get("/reports/monthly", response_model=Dict[str, Any])
async def get_monthly_report(
    year: int = Query(..., description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """获取月报表"""
    report = ReportService.get_monthly_report(db, year, month)
    return report

@router.get("/schedule-strategy", response_model=Dict[str, Any])
async def get_schedule_strategy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """获取当前调度策略"""
    from backend.app.core.config import get_station_config
    config = get_station_config()
    strategy = config.get("ScheduleStrategy", "default")
    bulk_size = config.get("BulkScheduleSize", 10)
    
    strategy_description = ""
    if strategy == "default":
        strategy_description = "默认调度：按照排队号码顺序依次调度"
    elif strategy == "batch_mode":
        strategy_description = "单次调度总充电时长最短：多辆车一次性调度，按充电模式分配对应充电桩，满足总充电时长最短"
    elif strategy == "bulk_mode":
        strategy_description = f"批量调度总充电时长最短：等待车辆数量达到{bulk_size}辆时才进行一次批量调度，忽略充电模式，满足总充电时长最短"
    
    return {
        "strategy": strategy,
        "description": strategy_description,
        "bulk_size": bulk_size
    }

@router.patch("/schedule-strategy", response_model=Dict[str, Any])
async def update_schedule_strategy(
    strategy: str = Query(..., description="调度策略 (default: 默认调度, batch_mode: 单次调度总充电时长最短, bulk_mode: 批量调度总充电时长最短)"),
    bulk_size: int = Query(10, ge=1, description="批量调度时的车辆数量，仅在bulk_mode模式下有效"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """更新调度策略"""
    # 验证策略有效性
    if strategy not in ["default", "batch_mode", "bulk_mode"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的调度策略: {strategy}"
        )
    
    # 更新配置文件
    import yaml
    import os
    from backend.app.core.config import CONFIG_PATH
    
    try:
        # 读取当前配置
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 更新调度策略
        if "station" not in config:
            config["station"] = {}
        
        config["station"]["ScheduleStrategy"] = strategy
        config["station"]["BulkScheduleSize"] = bulk_size
        
        # 写回配置文件
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        # 重新加载配置
        from backend.app.core.config import get_config
        get_config()  # 强制重新加载配置
        
        # 返回更新后的策略
        strategy_description = ""
        if strategy == "default":
            strategy_description = "默认调度：按照排队号码顺序依次调度"
        elif strategy == "batch_mode":
            strategy_description = "单次调度总充电时长最短：多辆车一次性调度，按充电模式分配对应充电桩，满足总充电时长最短"
        elif strategy == "bulk_mode":
            strategy_description = f"批量调度总充电时长最短：等待车辆数量达到{bulk_size}辆时才进行一次批量调度，忽略充电模式，满足总充电时长最短"
        
        return {
            "strategy": strategy,
            "description": strategy_description,
            "bulk_size": bulk_size,
            "message": "调度策略更新成功"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新调度策略失败: {str(e)}"
        ) 