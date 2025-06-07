import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.charging_service import ChargingService
from app.db.models import CarRequest, ChargePile, ChargeSession
from app.db.schemas import RequestStatus, ChargeMode

class TestChargingService(unittest.TestCase):
    """充电服务测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 创建模拟数据库会话
        self.db = MagicMock()
        
        # 模拟充电请求
        self.request = MagicMock(spec=CarRequest)
        self.request.id = 1
        self.request.user_id = "user1"
        self.request.pile_id = 1
        self.request.status = RequestStatus.CHARGING
        self.request.amount_kwh = 10.0
        self.request.start_time = datetime.now() - timedelta(minutes=30)
        
        # 模拟充电桩
        self.pile = MagicMock(spec=ChargePile)
        self.pile.id = 1
        self.pile.code = "A"
        self.pile.power = 30.0
        self.pile.type = "FAST"
        
        # 模拟充电会话
        self.session = MagicMock(spec=ChargeSession)
        self.session.id = 1
        self.session.request_id = 1
        self.session.pile_id = 1
        self.session.start_time = self.request.start_time
        self.session.status = "CHARGING"
        
        # 设置模拟查询结果
        self.db.query().filter().first.side_effect = [self.request, self.pile, self.session]
    
    @patch('app.services.billing.BillingService.calculate_charging_cost')
    @patch('app.services.scheduler.ChargingScheduler.finish_charging')
    def test_finish_charge_session(self, mock_finish_charging, mock_calculate_cost):
        """测试完成充电会话"""
        # 设置模拟返回值
        mock_calculate_cost.return_value = (20.0, 8.0, 28.0)  # 充电费, 服务费, 总费
        mock_finish_charging.return_value = (True, "成功完成充电")
        
        # 模拟生成账单
        with patch.object(ChargingService, 'generate_bill', return_value=MagicMock()):
            # 调用被测试的方法
            success, message, bill_detail = ChargingService.finish_charge_session(
                self.db, 1, 10.0, 30
            )
            
            # 验证结果
            self.assertTrue(success)
            self.assertEqual(self.session.charged_kwh, 10.0)
            self.assertEqual(self.session.charging_time, 30)
            self.assertEqual(self.session.charge_fee, 20.0)
            self.assertEqual(self.session.service_fee, 8.0)
            self.assertEqual(self.session.total_fee, 28.0)
            self.assertEqual(self.session.status, "COMPLETED")
            
            # 验证调用
            mock_calculate_cost.assert_called_once()
            mock_finish_charging.assert_called_once_with(self.db, 1)
    
    def test_get_charging_status(self):
        """测试获取充电状态"""
        # 设置模拟查询结果
        self.db.query().filter().first.side_effect = [self.request, self.pile]
        
        # 调用被测试的方法
        status = ChargingService.get_charging_status(self.db, 1)
        
        # 验证结果
        self.assertEqual(status["request_id"], 1)
        self.assertEqual(status["status"], RequestStatus.CHARGING)
        self.assertEqual(status["mode"], self.request.mode)
        self.assertEqual(status["amount_kwh"], 10.0)
        self.assertTrue("charging_progress" in status)
        self.assertTrue("charged_kwh" in status)
        self.assertTrue("charging_minutes" in status)
    
    def test_simulate_charging_progress(self):
        """测试模拟充电进度"""
        # 设置模拟查询结果
        self.db.query().filter().first.side_effect = [self.request, self.pile, self.session]
        
        # 模拟更新会话
        with patch.object(ChargingService, 'update_charge_session', return_value=(True, "")):
            # 调用被测试的方法
            success, message = ChargingService.simulate_charging_progress(self.db, 1, 50.0)
            
            # 验证结果
            self.assertTrue(success)
            self.assertTrue("50%" in message)

if __name__ == '__main__':
    unittest.main() 