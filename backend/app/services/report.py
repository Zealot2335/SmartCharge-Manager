from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, and_, extract
import csv
import io
import logging

from app.db.models import (
    ChargePile, ChargeSession, ReportDaily
)

logger = logging.getLogger(__name__)

class ReportService:
    """报表服务，处理统计数据和报表生成"""
    
    @staticmethod
    def generate_daily_report(db: Session, report_date: date) -> List[ReportDaily]:
        """生成指定日期的日报表"""
        # 删除已存在的同日报表
        db.query(ReportDaily).filter(ReportDaily.report_date == report_date).delete()
        
        # 查询所有充电桩
        piles = db.query(ChargePile).all()
        
        daily_reports = []
        
        for pile in piles:
            # 查询该充电桩当日的会话
            start_datetime = datetime.combine(report_date, datetime.min.time())
            end_datetime = datetime.combine(report_date, datetime.max.time())
            
            sessions = (
                db.query(ChargeSession)
                .filter(ChargeSession.pile_id == pile.id)
                .filter(ChargeSession.start_time >= start_datetime)
                .filter(ChargeSession.start_time <= end_datetime)
                .all()
            )
            
            # 计算统计数据
            charge_count = len(sessions)
            charge_time = sum(session.charging_time for session in sessions)
            charge_kwh = sum(session.charged_kwh for session in sessions)
            charge_fee = sum(session.charge_fee for session in sessions)
            service_fee = sum(session.service_fee for session in sessions)
            total_fee = sum(session.total_fee for session in sessions)
            
            # 创建日报表记录
            daily_report = ReportDaily(
                report_date=report_date,
                pile_id=pile.id,
                pile_code=pile.code,
                charge_count=charge_count,
                charge_time=charge_time,
                charge_kwh=charge_kwh,
                charge_fee=charge_fee,
                service_fee=service_fee,
                total_fee=total_fee
            )
            
            db.add(daily_report)
            daily_reports.append(daily_report)
        
        db.commit()
        
        # 刷新获取ID
        for report in daily_reports:
            db.refresh(report)
            
        return daily_reports
    
    @staticmethod
    def get_daily_report(db: Session, report_date: date) -> List[ReportDaily]:
        """获取日报表"""
        reports = db.query(ReportDaily).filter(ReportDaily.report_date == report_date).all()
        
        # 如果不存在，则生成
        if not reports:
            reports = ReportService.generate_daily_report(db, report_date)
            
        return reports
    
    @staticmethod
    def get_weekly_report(db: Session, date_in_week: date) -> Dict[str, Any]:
        """获取包含指定日期的周报表"""
        # 计算所在周的起止日期
        weekday = date_in_week.weekday()
        week_start = date_in_week - timedelta(days=weekday)
        week_end = week_start + timedelta(days=6)
        
        # 确保所有日报表都已生成
        for day in range(7):
            current_date = week_start + timedelta(days=day)
            if current_date <= date.today():  # 只生成到今天为止
                ReportService.get_daily_report(db, current_date)
        
        # 聚合周报表数据
        weekly_data = {}
        
        # 查询该周的所有日报表
        weekly_reports = (
            db.query(ReportDaily)
            .filter(ReportDaily.report_date >= week_start)
            .filter(ReportDaily.report_date <= week_end)
            .all()
        )
        
        # 按充电桩分组
        pile_reports = {}
        for report in weekly_reports:
            if report.pile_id not in pile_reports:
                pile_reports[report.pile_id] = {
                    "pile_id": report.pile_id,
                    "pile_code": report.pile_code,
                    "charge_count": 0,
                    "charge_time": 0,
                    "charge_kwh": 0.0,
                    "charge_fee": 0.0,
                    "service_fee": 0.0,
                    "total_fee": 0.0,
                    "daily_data": {}
                }
            
            # 累加统计数据
            pile_reports[report.pile_id]["charge_count"] += report.charge_count
            pile_reports[report.pile_id]["charge_time"] += report.charge_time
            pile_reports[report.pile_id]["charge_kwh"] += report.charge_kwh
            pile_reports[report.pile_id]["charge_fee"] += report.charge_fee
            pile_reports[report.pile_id]["service_fee"] += report.service_fee
            pile_reports[report.pile_id]["total_fee"] += report.total_fee
            
            # 记录日报表数据
            pile_reports[report.pile_id]["daily_data"][report.report_date.strftime("%Y-%m-%d")] = {
                "charge_count": report.charge_count,
                "charge_time": report.charge_time,
                "charge_kwh": report.charge_kwh,
                "charge_fee": report.charge_fee,
                "service_fee": report.service_fee,
                "total_fee": report.total_fee
            }
        
        # 计算总计
        total_data = {
            "charge_count": sum(pile["charge_count"] for pile in pile_reports.values()),
            "charge_time": sum(pile["charge_time"] for pile in pile_reports.values()),
            "charge_kwh": sum(pile["charge_kwh"] for pile in pile_reports.values()),
            "charge_fee": sum(pile["charge_fee"] for pile in pile_reports.values()),
            "service_fee": sum(pile["service_fee"] for pile in pile_reports.values()),
            "total_fee": sum(pile["total_fee"] for pile in pile_reports.values())
        }
        
        # 组装周报表
        weekly_data = {
            "week_start": week_start,
            "week_end": week_end,
            "total": total_data,
            "piles": list(pile_reports.values())
        }
        
        return weekly_data
    
    @staticmethod
    def get_monthly_report(db: Session, year: int, month: int) -> Dict[str, Any]:
        """获取月报表"""
        # 计算月份的起止日期
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)
        
        # 确保所有日报表都已生成
        current_date = first_day
        while current_date <= last_day and current_date <= date.today():
            ReportService.get_daily_report(db, current_date)
            current_date += timedelta(days=1)
        
        # 聚合月报表数据
        monthly_data = {}
        
        # 查询该月的所有日报表
        monthly_reports = (
            db.query(ReportDaily)
            .filter(ReportDaily.report_date >= first_day)
            .filter(ReportDaily.report_date <= last_day)
            .all()
        )
        
        # 按充电桩分组
        pile_reports = {}
        for report in monthly_reports:
            if report.pile_id not in pile_reports:
                pile_reports[report.pile_id] = {
                    "pile_id": report.pile_id,
                    "pile_code": report.pile_code,
                    "charge_count": 0,
                    "charge_time": 0,
                    "charge_kwh": 0.0,
                    "charge_fee": 0.0,
                    "service_fee": 0.0,
                    "total_fee": 0.0,
                    "weekly_data": {}
                }
            
            # 累加统计数据
            pile_reports[report.pile_id]["charge_count"] += report.charge_count
            pile_reports[report.pile_id]["charge_time"] += report.charge_time
            pile_reports[report.pile_id]["charge_kwh"] += report.charge_kwh
            pile_reports[report.pile_id]["charge_fee"] += report.charge_fee
            pile_reports[report.pile_id]["service_fee"] += report.service_fee
            pile_reports[report.pile_id]["total_fee"] += report.total_fee
            
            # 按周分组
            week_number = report.report_date.isocalendar()[1]
            if week_number not in pile_reports[report.pile_id]["weekly_data"]:
                pile_reports[report.pile_id]["weekly_data"][week_number] = {
                    "week_number": week_number,
                    "charge_count": 0,
                    "charge_time": 0,
                    "charge_kwh": 0.0,
                    "charge_fee": 0.0,
                    "service_fee": 0.0,
                    "total_fee": 0.0
                }
            
            # 累加周数据
            weekly_data = pile_reports[report.pile_id]["weekly_data"][week_number]
            weekly_data["charge_count"] += report.charge_count
            weekly_data["charge_time"] += report.charge_time
            weekly_data["charge_kwh"] += report.charge_kwh
            weekly_data["charge_fee"] += report.charge_fee
            weekly_data["service_fee"] += report.service_fee
            weekly_data["total_fee"] += report.total_fee
        
        # 计算总计
        total_data = {
            "charge_count": sum(pile["charge_count"] for pile in pile_reports.values()),
            "charge_time": sum(pile["charge_time"] for pile in pile_reports.values()),
            "charge_kwh": sum(pile["charge_kwh"] for pile in pile_reports.values()),
            "charge_fee": sum(pile["charge_fee"] for pile in pile_reports.values()),
            "service_fee": sum(pile["service_fee"] for pile in pile_reports.values()),
            "total_fee": sum(pile["total_fee"] for pile in pile_reports.values())
        }
        
        # 组装月报表
        monthly_data = {
            "year": year,
            "month": month,
            "first_day": first_day,
            "last_day": last_day,
            "total": total_data,
            "piles": list(pile_reports.values())
        }
        
        return monthly_data
    
    @staticmethod
    def export_daily_report_csv(db: Session, report_date: date) -> str:
        """导出日报表为CSV格式"""
        reports = ReportService.get_daily_report(db, report_date)
        
        # 创建CSV输出
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow([
            "日期", "充电桩编号", "累计充电次数", "累计充电时长(分钟)", 
            "累计充电量(kWh)", "累计充电费用(元)", "累计服务费用(元)", "累计总费用(元)"
        ])
        
        # 写入数据行
        for report in reports:
            writer.writerow([
                report.report_date.strftime("%Y-%m-%d"),
                report.pile_code,
                report.charge_count,
                report.charge_time,
                f"{report.charge_kwh:.2f}",
                f"{report.charge_fee:.2f}",
                f"{report.service_fee:.2f}",
                f"{report.total_fee:.2f}"
            ])
        
        # 写入总计行
        total_charge_count = sum(report.charge_count for report in reports)
        total_charge_time = sum(report.charge_time for report in reports)
        total_charge_kwh = sum(report.charge_kwh for report in reports)
        total_charge_fee = sum(report.charge_fee for report in reports)
        total_service_fee = sum(report.service_fee for report in reports)
        total_fee = sum(report.total_fee for report in reports)
        
        writer.writerow([
            report_date.strftime("%Y-%m-%d"),
            "总计",
            total_charge_count,
            total_charge_time,
            f"{total_charge_kwh:.2f}",
            f"{total_charge_fee:.2f}",
            f"{total_service_fee:.2f}",
            f"{total_fee:.2f}"
        ])
        
        return output.getvalue() 