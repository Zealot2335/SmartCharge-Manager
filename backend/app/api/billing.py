import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status, Query
from sqlalchemy import extract
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import date, datetime

from backend.app.db.database import get_db
from backend.app.db.models import User, BillMaster, BillDetail
from backend.app.core.auth import get_current_user
from backend.app.services.billing import BillingService

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/{bill_month}", response_model=List[Dict[str, Any]])
async def get_user_bill(
    bill_month: str = Path(..., description="账单月份，格式为YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户指定月份的所有详细账单（详单列表）
    """
    try:
        year, month = map(int, bill_month.split('-'))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="日期格式错误，应为 YYYY-MM"
        )

    # 查询该用户该月所有主账单
    bill_masters = (
        db.query(BillMaster)
        .filter(BillMaster.user_id == current_user.user_id)
        .filter(extract('year', BillMaster.bill_date) == year)
        .filter(extract('month', BillMaster.bill_date) == month)
        .all()
    )
    bill_ids = [bm.id for bm in bill_masters]
    if not bill_ids:
        return []

    # 查询所有详单
    details = (
        db.query(BillDetail)
        .filter(BillDetail.bill_id.in_(bill_ids))
        .order_by(BillDetail.start_time.desc())
        .all()
    )

    # 组装详单信息
    detail_list = []
    for detail in details:
        bill = next((bm for bm in bill_masters if bm.id == detail.bill_id), None)
        detail_list.append({
            "detail_number": detail.detail_number,
            "bill_date": bill.bill_date if bill else None,
            "pile_code": detail.pile_code,
            "charged_kwh": detail.charged_kwh,
            "charging_time": detail.charging_time,
            "start_time": detail.start_time,
            "end_time": detail.end_time,
            "charge_fee": detail.charge_fee,
            "service_fee": detail.service_fee,
            "total_fee": detail.total_fee,
        })

    return detail_list

@router.get("/detail/{detail_number}", response_model=Dict[str, Any])
async def get_bill_detail(
    detail_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取账单详单"""
    # 查询详单
    detail = BillingService.get_bill_detail_by_number(db, detail_number)
    
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到详单 {detail_number}"
        )
    
    # 查询账单
    bill = db.query(BillMaster).filter(BillMaster.id == detail.bill_id).first()
    
    if not bill or bill.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到详单 {detail_number}"
        )
    
    # 获取会话信息
    from backend.app.db.models import ChargeSession, ChargePile
    session = db.query(ChargeSession).filter(ChargeSession.id == detail.session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到详单 {detail_number} 对应的充电会话"
        )
    
    # 获取充电桩信息
    pile = db.query(ChargePile).filter(ChargePile.id == session.pile_id).first()
    
    # 获取充电请求信息
    from backend.app.db.models import CarRequest
    request = db.query(CarRequest).filter(CarRequest.id == session.request_id).first()
    
    # 构建详单信息
    detail_info = {
        "detail_number": detail.detail_number,
        "bill_date": bill.bill_date,
        "pile_code": detail.pile_code,
        "pile_type": pile.type if pile else None,
        "charged_kwh": detail.charged_kwh,
        "charging_time": detail.charging_time,
        "start_time": detail.start_time,
        "end_time": detail.end_time,
        "charge_fee": detail.charge_fee,
        "service_fee": detail.service_fee,
        "total_fee": detail.total_fee,
        "request_info": {
            "id": request.id if request else None,
            "queue_number": request.queue_number if request else None,
            "mode": request.mode if request else None,
            "amount_kwh": request.amount_kwh if request else None,
            "request_time": request.request_time if request else None
        } if request else None,
        "session_status": session.status
    }
    
    return detail_info

@router.get("/list/{year}-{month}", response_model=List[Dict[str, Any]])
async def get_monthly_bills(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取用户指定月份的所有账单"""
    try:
        if month < 1 or month > 12:
            raise ValueError("月份必须在1-12之间")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="月份格式错误，应为 YYYY-MM"
        )
    
    # 查询该月份的所有账单
    from sqlalchemy import extract
    bills = (
        db.query(BillMaster)
        .filter(BillMaster.user_id == current_user.user_id)
        .filter(extract('year', BillMaster.bill_date) == year)
        .filter(extract('month', BillMaster.bill_date) == month)
        .order_by(BillMaster.bill_date.desc())
        .all()
    )
    
    # 计算月度总计
    total_charge_fee = sum(bill.total_charge_fee for bill in bills)
    total_service_fee = sum(bill.total_service_fee for bill in bills)
    total_fee = sum(bill.total_fee for bill in bills)
    total_kwh = sum(bill.total_kwh for bill in bills)
    
    # 构建账单列表
    bill_list = []
    for bill in bills:
        bill_list.append({
            "bill_date": bill.bill_date,
            "total_charge_fee": bill.total_charge_fee,
            "total_service_fee": bill.total_service_fee,
            "total_fee": bill.total_fee,
            "total_kwh": bill.total_kwh
        })
    
    # 添加月度总计
    summary = {
        "year": year,
        "month": month,
        "total_charge_fee": total_charge_fee,
        "total_service_fee": total_service_fee,
        "total_fee": total_fee,
        "total_kwh": total_kwh,
        "bills": bill_list
    }
    
    # logger.info(f"用户 {current_user.user_id} 获取 {year}-{month} 月份账单列表 {len(bill_list)} 条记录")

    # 修改返回值为列表形式
    return [summary]

@router.get("/bills/{session_id}", response_model=Dict[str, Any])
async def get_bill_by_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """根据充电会话ID获取账单详情"""
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的会话ID"
        )
    
    # 查询充电会话
    from backend.app.db.models import ChargeSession, CarRequest
    session = db.query(ChargeSession).filter(ChargeSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到会话 {session_id}"
        )
    
    # 验证用户权限
    request = db.query(CarRequest).filter(CarRequest.id == session.request_id).first()
    if not request or request.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此会话"
        )
    
    # 查询账单详情
    detail = db.query(BillDetail).filter(BillDetail.session_id == session_id).first()
    
    if not detail:
        # 如果未找到详单但会话存在，尝试生成账单
        from backend.app.services.charging_service import ChargingService
        detail = ChargingService.generate_bill(db, session)
        if detail:
            db.commit()
    
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到会话 {session_id} 对应的账单"
        )
    
    # 获取充电桩信息
    from backend.app.db.models import ChargePile
    pile = db.query(ChargePile).filter(ChargePile.id == session.pile_id).first()
    
    # 获取账单主表
    bill = db.query(BillMaster).filter(BillMaster.id == detail.bill_id).first()
    
    # 构建详单信息
    detail_info = {
        "detail_number": detail.detail_number,
        "bill_date": bill.bill_date if bill else None,
        "pile_code": detail.pile_code,
        "pile_type": pile.type if pile else None,
        "charged_kwh": detail.charged_kwh,
        "charging_time": detail.charging_time,
        "start_time": detail.start_time,
        "end_time": detail.end_time,
        "charge_fee": detail.charge_fee,
        "service_fee": detail.service_fee,
        "total_fee": detail.total_fee,
        "request_info": {
            "id": request.id,
            "queue_number": request.queue_number,
            "mode": request.mode,
            "amount_kwh": request.amount_kwh,
            "request_time": request.request_time
        },
        "session_status": session.status
    }
    
    return detail_info 