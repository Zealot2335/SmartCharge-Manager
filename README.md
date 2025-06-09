# 智能充电桩调度计费系统

## 项目介绍

智能充电桩调度计费系统是一个用于电动汽车充电服务的全流程管理系统，包括充电请求、智能调度、充电监控和费用结算等功能。系统采用前后端分离架构，后端基于Python FastAPI框架开发，前端使用HTML、CSS和JavaScript构建。

## 系统功能

- **用户功能**
  - 用户注册与登录
  - 创建充电请求
  - 查看充电状态
  - 取消充电请求
  - 查看账单明细

- **管理员功能**
  - 充电桩管理
  - 充电请求监控
  - 费率管理
  - 报表统计

- **核心功能**
  - 智能调度算法
  - 实时充电监控
  - 动态费率计算
  - WebSocket实时通信

## 技术栈

- **后端**
  - Python 3.8+
  - FastAPI
  - SQLAlchemy
  - PyMySQL
  - WebSockets
  - JWT认证

- **前端**
  - HTML5
  - CSS3
  - JavaScript (原生)

- **数据库**
  - MySQL

## 系统架构

系统采用前后端分离的架构设计：

1. **前端**：提供用户界面，通过API与后端通信
2. **后端**：提供RESTful API和WebSocket服务
3. **数据库**：存储系统数据

## 快速开始

### 系统要求

- Python 3.8或更高版本
- MySQL 5.7或更高版本
- 现代浏览器（Chrome、Firefox、Edge等）

### 安装步骤

1. **克隆仓库**

```bash
git clone https://github.com/yourusername/smart-charge-manager.git
cd smart-charge-manager
```

2. **启动系统**

在Windows系统上，直接双击`start.bat`文件启动系统。

或者使用Python运行启动脚本：

```bash
python start.py
```

启动脚本会自动：
- 检查并安装依赖项
- 检查并初始化数据库
- 启动后端服务
- 打开浏览器访问系统

3. **访问系统**

系统启动后，浏览器会自动打开以下地址：

```
http://localhost:8000
```

### 默认账户

系统初始化后，会创建以下默认账户：

- 管理员账户
  - 用户名：admin
  - 密码：admin

- 测试用户账户
  - 用户名：user
  - 密码：admin

## 系统测试

运行测试脚本，测试后端API和前端连接：

```bash
python test_backend_frontend.py
```

## 目录结构

```
smart-charge-manager/
├── backend/                # 后端代码
│   ├── app/                # 应用代码
│   │   ├── api/            # API路由
│   │   ├── core/           # 核心配置
│   │   ├── db/             # 数据库模块
│   │   ├── models/         # 数据模型
│   │   ├── schemas/        # Pydantic模式
│   │   ├── services/       # 业务服务
│   │   └── main.py         # 应用入口
├── frontend/               # 前端代码
│   ├── admin/              # 管理员页面
│   ├── user/               # 用户页面
│   ├── static/             # 静态资源
│   │   ├── css/            # 样式表
│   │   ├── js/             # JavaScript
│   │   └── img/            # 图片资源
│   ├── index.html          # 首页
│   └── login.html          # 登录页
├── scripts/                # 脚本文件
│   └── init_db.sql         # 数据库初始化脚本
├── start.py                # Python启动脚本
├── start.bat               # Windows批处理启动脚本
├── test_backend_frontend.py # 测试脚本
└── README.md               # 项目说明
```

## 配置说明

系统配置文件位于`config.yml`，包含以下配置项：

- 系统配置：标题、版本、调试模式等
- 数据库配置：主机、端口、用户名、密码等
- 充电站配置：充电桩数量、等候区大小等
- 费率配置：电价费率、服务费率等

## 开发说明

### 后端开发

1. 安装开发依赖
```bash
pip install -r requirements-dev.txt
```

2. 运行开发服务器
```bash
uvicorn backend.app.main:app --reload
```

### 前端开发

前端采用原生HTML、CSS和JavaScript开发，无需构建工具。直接修改前端文件后刷新浏览器即可查看效果。
