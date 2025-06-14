# 智能充电桩调度计费系统 - 简化版启动说明

## 系统要求

- Python 3.8 或更高版本
- MySQL 数据库服务器
- 现代浏览器（Chrome、Firefox、Edge等）

## 快速启动

1. 确保MySQL服务已启动，并已创建用户名为`root`，密码为`20031216cyh`的账号

2. 使用以下方式之一启动系统：

   - **Windows用户**：双击 `start_simple.bat` 文件
   - **命令行用户**：运行 `python start_simple.py`

3. 系统启动后会同时运行：
   - 后端API服务：http://localhost:8000
   - 前端HTTP服务器：http://127.0.0.1:5500

4. 在浏览器中访问 http://127.0.0.1:5500 即可打开系统前端界面

## 默认账户

系统预设了两个账户供测试使用：

- **管理员账户**：
  - 用户名：admin
  - 密码：admin

- **普通用户账户**：
  - 用户名：user
  - 密码：admin

## 系统功能

- **用户功能**：
  - 提交充电请求
  - 查看充电状态
  - 修改/取消充电请求
  - 查看充电详单和账单

- **管理员功能**：
  - 查看所有充电桩状态
  - 管理充电桩
  - 查看统计报表
  - 处理故障

## 常见问题

1. **无法连接到数据库**
   - 确保MySQL服务已启动
   - 检查用户名和密码是否正确
   - 检查数据库端口是否为默认的3306

2. **端口被占用**
   - 如果8000或5500端口被其他程序占用，可以修改`start_simple.py`文件中的端口配置

3. **如何重置数据库**
   - 重新运行 `start_simple.py`，系统将检测并初始化数据库

## 技术支持

如有问题，请联系系统管理员。 