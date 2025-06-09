import os
import time
import subprocess
import requests
import webbrowser
from datetime import datetime

# 配置
BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:8000"
ADMIN_USER = {"username": "admin", "password": "admin"}
NORMAL_USER = {"username": "user", "password": "admin"}

def print_header(message):
    """打印带格式的标题"""
    print("\n" + "=" * 50)
    print(f"  {message}")
    print("=" * 50)

def test_backend_connection():
    """测试后端连接"""
    print_header("测试后端连接")
    
    try:
        response = requests.get(f"{BACKEND_URL}/api/health")
        if response.status_code == 200:
            print(f"✅ 后端连接成功: {response.json()}")
            return True
        else:
            print(f"❌ 后端连接失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 后端连接异常: {str(e)}")
        return False

def test_auth():
    """测试认证功能"""
    print_header("测试认证功能")
    
    # 测试管理员登录
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/auth/login",
            json=ADMIN_USER
        )
        
        if response.status_code == 200:
            admin_token = response.json().get("access_token")
            print(f"✅ 管理员登录成功")
            
            # 测试获取当前用户信息
            me_response = requests.get(
                f"{BACKEND_URL}/api/auth/me",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            if me_response.status_code == 200:
                print(f"✅ 获取管理员信息成功: {me_response.json()}")
            else:
                print(f"❌ 获取管理员信息失败: {me_response.status_code}")
        else:
            print(f"❌ 管理员登录失败: {response.status_code}")
            admin_token = None
    except Exception as e:
        print(f"❌ 管理员登录异常: {str(e)}")
        admin_token = None
    
    # 测试普通用户登录
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/auth/login",
            json=NORMAL_USER
        )
        
        if response.status_code == 200:
            user_token = response.json().get("access_token")
            print(f"✅ 普通用户登录成功")
            
            # 测试获取当前用户信息
            me_response = requests.get(
                f"{BACKEND_URL}/api/auth/me",
                headers={"Authorization": f"Bearer {user_token}"}
            )
            
            if me_response.status_code == 200:
                print(f"✅ 获取普通用户信息成功: {me_response.json()}")
            else:
                print(f"❌ 获取普通用户信息失败: {me_response.status_code}")
        else:
            print(f"❌ 普通用户登录失败: {response.status_code}")
            user_token = None
    except Exception as e:
        print(f"❌ 普通用户登录异常: {str(e)}")
        user_token = None
    
    return admin_token, user_token

def test_admin_apis(token):
    """测试管理员API"""
    print_header("测试管理员API")
    
    if not token:
        print("❌ 无管理员令牌，跳过测试")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 测试获取充电桩列表
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/admin/piles",
            headers=headers
        )
        
        if response.status_code == 200:
            piles = response.json()
            print(f"✅ 获取充电桩列表成功，共{len(piles)}个充电桩")
        else:
            print(f"❌ 获取充电桩列表失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取充电桩列表异常: {str(e)}")
    
    # 测试获取费率规则
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/admin/rates",
            headers=headers
        )
        
        if response.status_code == 200:
            rates = response.json()
            print(f"✅ 获取费率规则成功，共{len(rates)}条规则")
        else:
            print(f"❌ 获取费率规则失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取费率规则异常: {str(e)}")
    
    # 测试获取服务费率
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/admin/service-rate",
            headers=headers
        )
        
        if response.status_code == 200:
            service_rate = response.json()
            print(f"✅ 获取服务费率成功: {service_rate}")
        else:
            print(f"❌ 获取服务费率失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取服务费率异常: {str(e)}")

def test_user_apis(token):
    """测试用户API"""
    print_header("测试用户API")
    
    if not token:
        print("❌ 无用户令牌，跳过测试")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    request_id = None
    
    # 测试创建充电请求
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/charging/request",
            headers=headers,
            json={
                "mode": "FAST",
                "amount_kwh": 10.0,
                "battery_capacity": 60.0
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            request_id = result.get("id")
            print(f"✅ 创建充电请求成功，ID: {request_id}，排队号: {result.get('queue_number')}")
        else:
            print(f"❌ 创建充电请求失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 创建充电请求异常: {str(e)}")
    
    # 如果创建成功，测试获取请求详情
    if request_id:
        try:
            response = requests.get(
                f"{BACKEND_URL}/api/charging/{request_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 获取充电请求详情成功，状态: {result.get('status')}")
            else:
                print(f"❌ 获取充电请求详情失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 获取充电请求详情异常: {str(e)}")
        
        # 测试获取充电状态
        try:
            response = requests.get(
                f"{BACKEND_URL}/api/charging/{request_id}/state",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 获取充电状态成功，进度: {result.get('progress')}%")
            else:
                print(f"❌ 获取充电状态失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 获取充电状态异常: {str(e)}")
        
        # 测试模拟充电进度
        try:
            response = requests.post(
                f"{BACKEND_URL}/api/charging/{request_id}/simulate",
                headers=headers,
                params={"progress": 50.0}
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 模拟充电进度成功，新进度: {result.get('progress')}%")
            else:
                print(f"❌ 模拟充电进度失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 模拟充电进度异常: {str(e)}")
    
    # 测试获取队列信息
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/charging/queue/FAST",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 获取快充队列信息成功，等候区: {result.get('waiting_count')}辆，充电区: {result.get('charging_count')}辆")
        else:
            print(f"❌ 获取快充队列信息失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取快充队列信息异常: {str(e)}")

def test_frontend():
    """测试前端页面加载"""
    print_header("测试前端页面加载")
    
    pages = [
        "/",
        "/login.html",
        "/user/requests.html",
        "/admin/index.html"
    ]
    
    for page in pages:
        try:
            response = requests.get(f"{FRONTEND_URL}{page}")
            if response.status_code == 200:
                print(f"✅ 页面 {page} 加载成功")
            else:
                print(f"❌ 页面 {page} 加载失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 页面 {page} 加载异常: {str(e)}")

def open_frontend():
    """打开前端页面"""
    print_header("打开前端页面")
    
    try:
        print("正在打开前端页面...")
        webbrowser.open(FRONTEND_URL)
        print("✅ 已打开前端页面")
    except Exception as e:
        print(f"❌ 打开前端页面失败: {str(e)}")

def main():
    """主测试函数"""
    print_header("智能充电桩调度计费系统 - 测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试后端连接
    if not test_backend_connection():
        print("\n❌ 后端连接失败，请确保后端服务已启动")
        return
    
    # 测试认证
    admin_token, user_token = test_auth()
    
    # 测试管理员API
    test_admin_apis(admin_token)
    
    # 测试用户API
    test_user_apis(user_token)
    
    # 测试前端页面加载
    test_frontend()
    
    # 打开前端页面
    open_frontend()
    
    print("\n✅ 测试完成")

if __name__ == "__main__":
    main() 