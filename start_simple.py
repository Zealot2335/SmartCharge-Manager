import os
import sys
import time
import subprocess
import threading
import http.server
import socketserver
from pathlib import Path

def print_header(message):
    """打印带格式的标题"""
    print("\n" + "=" * 50)
    print(f"  {message}")
    print("=" * 50)

def check_dependencies():
    """检查依赖项"""
    print_header("检查依赖项")
    
    required_packages = [
        "uvicorn", "fastapi", "pymysql", "sqlalchemy", 
        "pydantic", "websockets", "passlib", "python-jose"
    ]
    
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"✅ {package} 已安装")
        except ImportError:
            print(f"❌ {package} 未安装，正在安装...")
            subprocess.run([sys.executable, "-m", "pip", "install", package], check=False)

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
                "--port", str(port)
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

class FrontendHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义HTTP请求处理器，用于提供前端文件"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path("frontend").absolute()), **kwargs)
    
    def log_message(self, format, *args):
        print(f"[前端] {args[0]} {args[1]} {args[2]}")

def start_frontend_server(port=5500):
    """启动前端HTTP服务器"""
    print_header(f"启动前端HTTP服务器 (端口: {port})")
    
    # 检查前端目录是否存在
    frontend_dir = Path("frontend")
    if not frontend_dir.exists() or not frontend_dir.is_dir():
        print(f"❌ 前端目录不存在: {frontend_dir}")
        return None
    
    try:
        # 创建HTTP服务器
        httpd = socketserver.TCPServer(("", port), FrontendHTTPRequestHandler)
        
        # 启动服务器线程
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        
        print(f"✅ 前端HTTP服务器已启动，监听端口: {port}")
        print(f"\n请在浏览器中访问: http://127.0.0.1:{port}")
        
        return httpd
    except Exception as e:
        print(f"❌ 启动前端HTTP服务器异常: {str(e)}")
        return None

def main():
    """主函数"""
    print_header("智能充电桩调度计费系统 - 简易启动器")
    
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
    backend_process = start_backend(port=8000)
    if not backend_process:
        print("❌ 后端服务启动失败，无法继续")
        return
    
    # 启动前端HTTP服务器
    frontend_server = start_frontend_server(port=5500)
    if not frontend_server:
        print("❌ 前端HTTP服务器启动失败")
        backend_process.terminate()
        return
    
    print("\n系统已启动，按 Ctrl+C 停止服务")
    
    try:
        # 保持程序运行，直到用户按下Ctrl+C
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        
        # 停止前端HTTP服务器
        if frontend_server:
            frontend_server.shutdown()
            print("✅ 前端HTTP服务器已停止")
        
        # 停止后端服务
        if backend_process:
            backend_process.terminate()
            backend_process.wait()
            print("✅ 后端服务已停止")
        
        print("✅ 系统已关闭")

if __name__ == "__main__":
    main() 