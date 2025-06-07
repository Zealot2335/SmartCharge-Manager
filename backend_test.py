import requests
import json
import time
from datetime import datetime

# 测试配置
BASE_URL = "http://localhost:8000/api"
TOKEN = None

def print_result(name, response):
    """打印测试结果"""
    print(f"\n=== {name} ===")
    print(f"状态码: {response.status_code}")
    try:
        print(f"响应内容: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
    except:
        print(f"响应内容: {response.text}")

def test_login():
    """测试登录功能"""
    global TOKEN
    
    # 测试管理员登录
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    print_result("管理员登录", response)
    
    if response.status_code == 200:
        TOKEN = response.json().get("access_token")
        print(f"获取Token: {TOKEN}")
    
    # 测试普通用户登录
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "user", "password": "admin"}
    )
    print_result("用户登录", response)

def test_charging_request():
    """测试充电请求功能"""
    global TOKEN
    
    if not TOKEN:
        print("无法测试充电请求：未获取到Token")
        return
    
    # 创建充电请求
    headers = {"Authorization": f"Bearer {TOKEN}"}
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
    
    if response.status_code != 200:
        print("创建充电请求失败，无法继续测试")
        return
    
    request_id = response.json().get("id")
    
    # 获取充电请求详情
    response = requests.get(
        f"{BASE_URL}/charging/{request_id}",
        headers=headers
    )
    print_result("获取充电请求详情", response)
    
    # 获取充电状态
    response = requests.get(
        f"{BASE_URL}/charging/{request_id}/state",
        headers=headers
    )
    print_result("获取充电状态", response)
    
    # 获取队列信息
    response = requests.get(
        f"{BASE_URL}/charging/queue/FAST",
        headers=headers
    )
    print_result("获取队列信息", response)
    
    # 模拟充电进度
    response = requests.post(
        f"{BASE_URL}/charging/{request_id}/simulate",
        headers=headers,
        params={"progress": 50.0}
    )
    print_result("模拟充电进度(50%)", response)
    
    # 再次获取充电状态
    response = requests.get(
        f"{BASE_URL}/charging/{request_id}/state",
        headers=headers
    )
    print_result("获取更新后的充电状态", response)
    
    # 模拟充电完成
    response = requests.post(
        f"{BASE_URL}/charging/{request_id}/simulate",
        headers=headers,
        params={"progress": 100.0}
    )
    print_result("模拟充电完成(100%)", response)
    
    # 获取完成后的充电状态
    response = requests.get(
        f"{BASE_URL}/charging/{request_id}/state",
        headers=headers
    )
    print_result("获取充电完成后的状态", response)

def test_billing():
    """测试账单功能"""
    global TOKEN
    
    if not TOKEN:
        print("无法测试账单功能：未获取到Token")
        return
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # 获取当日账单
    today = datetime.now().strftime("%Y-%m-%d")
    response = requests.get(
        f"{BASE_URL}/billing/daily/{today}",
        headers=headers
    )
    print_result(f"获取{today}的账单", response)

def test_admin_functions():
    """测试管理员功能"""
    global TOKEN
    
    if not TOKEN:
        print("无法测试管理员功能：未获取到Token")
        return
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # 获取充电桩列表
    response = requests.get(
        f"{BASE_URL}/admin/piles",
        headers=headers
    )
    print_result("获取充电桩列表", response)
    
    # 获取费率规则
    response = requests.get(
        f"{BASE_URL}/admin/rates",
        headers=headers
    )
    print_result("获取费率规则", response)

def main():
    """主测试函数"""
    print("开始后端API测试...")
    
    # 测试登录
    test_login()
    
    # 测试充电请求功能
    test_charging_request()
    
    # 测试账单功能
    test_billing()
    
    # 测试管理员功能
    test_admin_functions()
    
    print("\n测试完成!")

if __name__ == "__main__":
    main() 