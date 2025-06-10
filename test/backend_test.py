import pytest
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api"

@pytest.fixture(scope="session")
def token():
    """获取并返回管理员Token"""
    data = {
        "username": "admin",
        "password": "admin"
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(
        f"{BASE_URL}/auth/login",
        headers=headers,
        data=data
    )
    assert response.status_code == 200, "管理员登录失败"
    return response.json().get("access_token")

def print_result(name, response):
    print(f"\n=== {name} ===")
    print(f"状态码: {response.status_code}")
    try:
        print(f"响应内容: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
    except Exception:
        print(f"响应内容: {response.text}")

def test_login(token):
    """测试管理员登录"""
    assert token is not None
    print(f"获取Token: {token}")

@pytest.fixture(scope="session")
def user_token():
    """获取并返回普通用户Token"""
    data = {
        "username": "user",
        "password": "admin"
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(
        f"{BASE_URL}/auth/login",
        headers=headers,
        data=data
    )
    assert response.status_code == 200, "用户登录失败"
    return response.json().get("access_token")

def test_charging_request(token):
    """测试充电请求功能"""
    headers = {"Authorization": f"Bearer {token}"}
    # 创建充电请求
    response = requests.post(
        f"{BASE_URL}/charging/request",
        headers=headers,
        json={
            "mode": "FAST",
            "amount_kwh": 10.0,
            "battery_capacity": 60.0
        }
    )
    print_result("创建充电请求", response)
    assert response.status_code == 200
    request_id = response.json().get("id")

    # 获取充电请求详情
    response = requests.get(
        f"{BASE_URL}/charging/{request_id}",
        headers=headers
    )
    print_result("获取充电请求详情", response)
    assert response.status_code == 200

    # 获取充电状态
    response = requests.get(
        f"{BASE_URL}/charging/{request_id}/state",
        headers=headers
    )
    print_result("获取充电状态", response)
    assert response.status_code == 200

    # 获取队列信息
    response = requests.get(
        f"{BASE_URL}/charging/queue/FAST",
        headers=headers
    )
    print_result("获取队列信息", response)
    assert response.status_code == 200

    # 模拟充电进度
    response = requests.post(
        f"{BASE_URL}/charging/{request_id}/simulate",
        headers=headers,
        params={"progress": 50.0}
    )
    print_result("模拟充电进度(50%)", response)
    assert response.status_code == 200

    # 再次获取充电状态
    response = requests.get(
        f"{BASE_URL}/charging/{request_id}/state",
        headers=headers
    )
    print_result("获取更新后的充电状态", response)
    assert response.status_code == 200

    # 模拟充电完成
    response = requests.post(
        f"{BASE_URL}/charging/{request_id}/simulate",
        headers=headers,
        params={"progress": 100.0}
    )
    print_result("模拟充电完成(100%)", response)
    assert response.status_code == 200

    # 获取完成后的充电状态
    response = requests.get(
        f"{BASE_URL}/charging/{request_id}/state",
        headers=headers
    )
    print_result("获取充电完成后的状态", response)
    assert response.status_code == 200

def test_billing(token):
    """测试账单功能"""
    headers = {"Authorization": f"Bearer {token}"}
    today = datetime.now()
    year = today.year
    month = today.month
    # 获取当月账单列表（路由已规范为 /billing/month/{year}-{month}）
    response = requests.get(
        f"{BASE_URL}/billing/month/{year}-{month}",
        headers=headers
    )
    print_result(f"获取{year}-{month}的账单", response)
    assert response.status_code == 200

    # 可选：获取某个详单（假设有返回且有detail_number字段）
    # bill_list = response.json()
    # if bill_list and "detail_number" in bill_list[0]:
    #     detail_number = bill_list[0]["detail_number"]
    #     response = requests.get(
    #         f"{BASE_URL}/billing/detail/{detail_number}",
    #         headers=headers
    #     )
    #     print_result(f"获取详单 {detail_number}", response)
    #     assert response.status_code == 200

    # 可选：获取某个会话账单（假设有session_id字段）
    # if bill_list and "session_id" in bill_list[0]:
    #     session_id = bill_list[0]["session_id"]
    #     response = requests.get(
    #         f"{BASE_URL}/billing/session/{session_id}",
    #         headers=headers
    #     )
    #     print_result(f"获取会话账单 {session_id}", response)
    #     assert response.status_code == 200

def test_admin_functions(token):
    """测试管理员功能"""
    headers = {"Authorization": f"Bearer {token}"}
    # 获取充电桩列表
    response = requests.get(
        f"{BASE_URL}/admin/piles",
        headers=headers
    )
    print_result("获取充电桩列表", response)
    assert response.status_code == 200

    # 获取费率规则
    response = requests.get(
        f"{BASE_URL}/admin/rates",
        headers=headers
    )
    print_result("获取费率规则", response)
    assert response.status_code == 200

if __name__ == "__main__":
    pytest.main(["-v", "test/backend_test.py"])