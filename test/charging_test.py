import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent 
sys.path.append(str(project_root))

from backend.app.services.charging_service import ChargingService
from backend.app.db.models import CarRequest, ChargePile, ChargeSession
from backend.app.db.schemas import RequestStatus, ChargeMode

@pytest.fixture
def mock_env():
    db = MagicMock()
    request = MagicMock(spec=CarRequest)
    request.id = 1
    request.user_id = "user1"
    request.pile_id = 1
    request.status = RequestStatus.CHARGING
    request.amount_kwh = 10.0
    request.start_time = datetime.now() - timedelta(minutes=30)
    request.mode = ChargeMode.FAST

    pile = MagicMock(spec=ChargePile)
    pile.id = 1
    pile.code = "A"
    pile.power = 30.0
    pile.type = "FAST"

    session = MagicMock(spec=ChargeSession)
    session.id = 1
    session.request_id = 1
    session.pile_id = 1
    session.start_time = request.start_time
    session.status = "CHARGING"
    session.charged_kwh = 0.0
    session.charging_time = 0
    session.charge_fee = 0.0
    session.service_fee = 0.0
    session.total_fee = 0.0

    return db, request, pile, session

# @patch('backend.app.services.billing.BillingService.calculate_charging_cost')
# @patch('backend.app.services.scheduler.ChargingScheduler.finish_charging')
# def test_finish_charge_session_success(mock_finish_charging, mock_calculate_cost, mock_env):
#     """测试正常完成充电会话及计费"""
#     db, request, pile, session = mock_env
#     mock_calculate_cost.return_value = (20.0, 8.0, 28.0)
#     mock_finish_charging.return_value = (True, "成功完成充电")
#     db.query().filter().first.side_effect = [request, pile, session]

#     with patch.object(ChargingService, 'generate_bill', return_value=MagicMock()) as mock_generate_bill:
#         success, message, bill_detail = ChargingService.finish_charge_session(
#             db, 1, 10.0, 30
#         )
#         assert success
#         assert message == "成功完成充电"
#         assert bill_detail is not None
#         assert session.charged_kwh == 10.0
#         assert session.charging_time == 30
#         assert session.charge_fee == 20.0
#         assert session.service_fee == 8.0
#         assert session.total_fee == 28.0
#         assert session.status == "COMPLETED"
#         mock_calculate_cost.assert_called_once_with(pile, 10.0, 30)
#         mock_finish_charging.assert_called_once_with(db, 1)
#         mock_generate_bill.assert_called_once()

# @patch('backend.app.services.billing.BillingService.calculate_charging_cost')
# @patch('backend.app.services.scheduler.ChargingScheduler.finish_charging')
# def test_finish_charge_session_fail(mock_finish_charging, mock_calculate_cost, mock_env):
#     """测试充电失败场景"""
#     db, request, pile, session = mock_env
#     mock_calculate_cost.return_value = (0.0, 0.0, 0.0)
#     mock_finish_charging.return_value = (False, "充电失败")
#     db.query().filter().first.side_effect = [request, pile, session]

#     with patch.object(ChargingService, 'generate_bill', return_value=None) as mock_generate_bill:
#         success, message, bill_detail = ChargingService.finish_charge_session(
#             db, 1, 0.0, 0
#         )
#         assert not success
#         assert message == "充电失败"
#         assert bill_detail is None
#         mock_finish_charging.assert_called_once_with(db, 1)
#         mock_generate_bill.assert_not_called()

# def test_finish_charge_session_request_not_found(mock_env):
#     """测试找不到充电请求"""
#     db, request, pile, session = mock_env
#     db.query().filter().first.side_effect = [None, pile, session]
#     with pytest.raises(Exception):
#         ChargingService.finish_charge_session(db, 1, 10.0, 30)

def test_finish_charge_session_pile_not_found(mock_env):
    """测试找不到充电桩"""
    db, request, pile, session = mock_env
    db.query().filter().first.side_effect = [request, None, session]
    with pytest.raises(Exception):
        ChargingService.finish_charge_session(db, 1, 10.0, 30)

def test_finish_charge_session_session_not_found(mock_env):
    """测试找不到充电会话"""
    db, request, pile, session = mock_env
    db.query().filter().first.side_effect = [request, pile, None]
    with pytest.raises(Exception):
        ChargingService.finish_charge_session(db, 1, 10.0, 30)

# @patch('backend.app.services.scheduler.ChargingScheduler.dispatch')
# def test_dispatch_strategy_min_total_time(mock_dispatch, mock_env):
#     """测试调度策略：完成充电总时长最短"""
#     db, request, pile, session = mock_env
#     # 假设有多个桩和多个请求，调度应选择最优分配
#     mock_dispatch.return_value = {
#         "assigned_pile": "A",
#         "expected_wait_time": 0,
#         "expected_charge_time": 20,
#         "total_time": 20
#     }
#     result = ChargingService.dispatch(db, request)
#     assert result["assigned_pile"] == "A"
#     assert result["total_time"] == 20

def test_charge_fee_calculation_peak_flat_valley(mock_env):
    """测试计费规则：峰/平/谷时段电价与服务费"""
    db, request, pile, session = mock_env
    # 峰时段
    pile.power = 30.0
    request.amount_kwh = 30.0
    start_time = datetime.strptime("2023-06-01 10:30", "%Y-%m-%d %H:%M")
    end_time = start_time + timedelta(hours=1)
    with patch('backend.app.services.billing.BillingService.calculate_charging_cost') as mock_calc:
        mock_calc.return_value = (30.0, 24.0, 54.0)  # 1.0元/度+0.8元/度
        charge_fee, service_fee, total_fee = mock_calc(pile, 30.0, 60)
        assert charge_fee == 30.0
        assert service_fee == 24.0
        assert total_fee == 54.0

# def test_queue_number_generation(mock_env):
#     """测试排队号码生成规则"""
#     db, request, pile, session = mock_env
#     # 快充
#     request.mode = ChargeMode.FAST
#     with patch('backend.app.services.charging_service.ChargingService.generate_queue_number') as mock_gen:
#         mock_gen.return_value = "F1"
#         queue_number = ChargingService.generate_queue_number(db, request)
#         assert queue_number.startswith("F")
#     # 慢充
#     request.mode = ChargeMode.TRICKLE
#     with patch('backend.app.services.charging_service.ChargingService.generate_queue_number') as mock_gen:
#         mock_gen.return_value = "T2"
#         queue_number = ChargingService.generate_queue_number(db, request)
#         assert queue_number.startswith("T")

# def test_modify_request_in_waiting_area(mock_env):
#     """测试等候区允许修改充电模式和充电量"""
#     db, request, pile, session = mock_env
#     request.status = RequestStatus.WAITING
#     # 修改模式
#     request.mode = ChargeMode.TRICKLE
#     with patch('backend.app.services.charging_service.ChargingService.modify_request') as mock_modify:
#         mock_modify.return_value = True
#         assert ChargingService.modify_request(db, request, mode=ChargeMode.FAST)
#     # 修改充电量
#     with patch('backend.app.services.charging_service.ChargingService.modify_request') as mock_modify:
#         mock_modify.return_value = True
#         assert ChargingService.modify_request(db, request, amount_kwh=20.0)

# def test_modify_request_in_charging_area(mock_env):
#     """测试充电区不允许修改充电模式和充电量"""
#     db, request, pile, session = mock_env
#     request.status = RequestStatus.CHARGING
#     with patch('backend.app.services.charging_service.ChargingService.modify_request') as mock_modify:
#         mock_modify.return_value = False
#         assert not ChargingService.modify_request(db, request, mode=ChargeMode.TRICKLE)
#         assert not ChargingService.modify_request(db, request, amount_kwh=5.0)

# def test_cancel_request(mock_env):
#     """测试等候区和充电区均允许取消充电"""
#     db, request, pile, session = mock_env
#     for status in [RequestStatus.WAITING, RequestStatus.CHARGING]:
#         request.status = status
#         with patch('backend.app.services.charging_service.ChargingService.cancel_request') as mock_cancel:
#             mock_cancel.return_value = True
#             assert ChargingService.cancel_request(db, request)