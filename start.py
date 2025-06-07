import os
import sys
import time
import webbrowser
import subprocess
import signal
import threading
from pathlib import Path

def print_header(message):
    """打印带格式的标题"""
    print("\n" + "=" * 50)
    print(f"  {message}")
    print("=" * 50)

def check_dependencies():
    """检查依赖项"""
    print_header("检查依赖项")
    
    try:
        import uvicorn
        print("✅ uvicorn 已安装")
    except ImportError:
        print("❌ uvicorn 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "uvicorn"], check=True)
    
    try:
        import fastapi
        print("✅ fastapi 已安装")
    except ImportError:
        print("❌ fastapi 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "fastapi"], check=True)
    
    try:
        import pymysql
        print("✅ pymysql 已安装")
    except ImportError:
        print("❌ pymysql 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pymysql"], check=True)
    
    try:
        import sqlalchemy
        print("✅ sqlalchemy 已安装")
    except ImportError:
        print("❌ sqlalchemy 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "sqlalchemy"], check=True)
    
    try:
        import pydantic
        print("✅ pydantic 已安装")
    except ImportError:
        print("❌ pydantic 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pydantic"], check=True)
    
    try:
        import websockets
        print("✅ websockets 已安装")
    except ImportError:
        print("❌ websockets 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "websockets"], check=True)
    
    try:
        import python_jose
        print("✅ python-jose 已安装")
    except ImportError:
        print("❌ python-jose 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "python-jose[cryptography]"], check=True)
    
    try:
        import passlib
        print("✅ passlib 已安装")
    except ImportError:
        print("❌ passlib 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "passlib[bcrypt]"], check=True)
    
    print("✅ 所有依赖项已安装")

def check_database():
    """检查数据库连接"""
    print_header("检查数据库连接")
    
    try:
        import pymysql
        
        # 尝试连接数据库
        connection = pymysql.connect(
            host="localhost",
            user="root",
            password="20031216cyh",
            database="smart_charge"
        )
        
        # 检查数据库是否存在
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            if not tables:
                print("⚠️ 数据库表不存在，需要初始化数据库")
                return False
            else:
                print(f"✅ 数据库连接成功，共有 {len(tables)} 个表")
                return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {str(e)}")
        return False

def init_database():
    """初始化数据库"""
    print_header("初始化数据库")
    
    try:
        # 检查初始化脚本是否存在
        script_path = Path("scripts/init_basic.sql")
        if not script_path.exists():
            print(f"❌ 初始化脚本不存在: {script_path}")
            return False
        
        # 执行MySQL命令
        print("正在执行数据库初始化脚本...")
        result = subprocess.run(
            ["mysql", "-u", "root", "-p20031216cyh", "-e", f"source {script_path}"],
            capture_output=True
        )
        
        if result.returncode == 0:
            print("✅ 数据库初始化成功")
            return True
        else:
            print(f"❌ 数据库初始化失败: {result.stderr.decode()}")
            return False
    except Exception as e:
        print(f"❌ 数据库初始化异常: {str(e)}")
        return False

def start_backend(port=8000):
    """启动后端服务"""
    print_header(f"启动后端服务 (端口: {port})")
    
    # 检查后端目录是否存在
    backend_dir = Path("backend")
    if not backend_dir.exists() or not backend_dir.is_dir():
        print(f"❌ 后端目录不存在: {backend_dir}")
        return None
    
    try:
        # 启动后端服务
        print("正在启动后端服务...")
        
        # 使用uvicorn启动FastAPI应用
        backend_process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", 
                "backend.app.main:app", 
                "--host", "0.0.0.0", 
                "--port", str(port),
                "--reload"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 启动日志监控线程
        def monitor_logs():
            while True:
                line = backend_process.stdout.readline()
                if not line and backend_process.poll() is not None:
                    break
                if line:
                    print(f"[后端] {line.strip()}")
        
        log_thread = threading.Thread(target=monitor_logs, daemon=True)
        log_thread.start()
        
        # 等待服务启动
        print("等待后端服务启动...")
        time.sleep(2)
        
        # 检查服务是否正常启动
        if backend_process.poll() is not None:
            print(f"❌ 后端服务启动失败: {backend_process.stderr.read()}")
            return None
        
        print(f"✅ 后端服务已启动，监听端口: {port}")
        return backend_process
    except Exception as e:
        print(f"❌ 启动后端服务异常: {str(e)}")
        return None

def open_browser(url):
    """打开浏览器"""
    print(f"正在打开浏览器: {url}")
    webbrowser.open(url)

def main():
    """主函数"""
    print_header("智能充电桩调度计费系统 - 启动器")
    
    # 检查依赖项
    check_dependencies()
    
    # 检查数据库
    db_ok = check_database()
    if not db_ok:
        # 初始化数据库
        db_ok = init_database()
        if not db_ok:
            print("❌ 数据库初始化失败，无法继续")
            return
    
    # 启动后端服务
    backend_process = start_backend()
    if not backend_process:
        print("❌ 后端服务启动失败，无法继续")
        return
    
    # 等待服务完全启动
    print("等待服务完全启动...")
    time.sleep(3)
    
    # 打开浏览器
    open_browser("http://localhost:8000")
    
    print("\n系统已启动，按 Ctrl+C 停止服务")
    
    try:
        # 保持程序运行，直到用户按下Ctrl+C
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        
        # 停止后端服务
        if backend_process:
            backend_process.terminate()
            backend_process.wait()
            print("✅ 后端服务已停止")
        
        print("✅ 系统已关闭")

if __name__ == "__main__":
    main() 