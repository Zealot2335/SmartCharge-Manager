-- 创建数据库
CREATE DATABASE IF NOT EXISTS smart_charge DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE smart_charge;

-- 充电桩表
CREATE TABLE IF NOT EXISTS t_charge_pile (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(10) NOT NULL COMMENT '桩编号，如A、B、C等',
    type ENUM('FAST', 'SLOW') NOT NULL COMMENT '桩类型，快充或慢充',
    status ENUM('AVAILABLE', 'BUSY', 'FAULT', 'OFFLINE') NOT NULL DEFAULT 'OFFLINE' COMMENT '桩状态',
    power DECIMAL(10,2) NOT NULL COMMENT '充电功率 kWh/h',
    total_charge_count INT NOT NULL DEFAULT 0 COMMENT '累计充电次数',
    total_charge_time INT NOT NULL DEFAULT 0 COMMENT '累计充电时长(分钟)',
    total_charge_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '累计充电度数',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_pile_code (code)
) COMMENT='充电桩信息表';

-- 充电请求表
CREATE TABLE IF NOT EXISTS t_car_request (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL COMMENT '用户ID',
    queue_number VARCHAR(20) NOT NULL COMMENT '排队号码，如F1、T2等',
    mode ENUM('FAST', 'SLOW') NOT NULL COMMENT '充电模式，快充或慢充',
    amount_kwh DECIMAL(10,2) NOT NULL COMMENT '请求充电量(kWh)',
    battery_capacity DECIMAL(10,2) NOT NULL COMMENT '电池总容量(kWh)',
    status ENUM('WAITING', 'QUEUING', 'CHARGING', 'FINISHED', 'CANCELED') NOT NULL DEFAULT 'WAITING' COMMENT '请求状态',
    pile_id INT NULL COMMENT '分配的充电桩ID',
    queue_position INT NULL COMMENT '在充电桩队列中的位置',
    request_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '请求时间',
    start_time TIMESTAMP NULL COMMENT '开始充电时间',
    end_time TIMESTAMP NULL COMMENT '结束充电时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_queue_number (queue_number),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_pile_id (pile_id)
) COMMENT='充电请求表';

-- 充电会话表
CREATE TABLE IF NOT EXISTS t_charge_session (
    id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL COMMENT '关联的充电请求ID',
    pile_id INT NOT NULL COMMENT '充电桩ID',
    start_time TIMESTAMP NOT NULL COMMENT '会话开始时间',
    end_time TIMESTAMP NULL COMMENT '会话结束时间',
    charged_kwh DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '充电电量(kWh)',
    charging_time INT NOT NULL DEFAULT 0 COMMENT '充电时长(分钟)',
    charge_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '充电费用',
    service_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '服务费用',
    total_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '总费用',
    status ENUM('CHARGING', 'COMPLETED', 'INTERRUPTED') NOT NULL DEFAULT 'CHARGING' COMMENT '会话状态',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_request_id (request_id),
    INDEX idx_pile_id (pile_id)
) COMMENT='充电会话表';

-- 账单主表
CREATE TABLE IF NOT EXISTS t_bill_master (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL COMMENT '用户ID',
    bill_date DATE NOT NULL COMMENT '账单日期',
    total_charge_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '总充电费用',
    total_service_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '总服务费用',
    total_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '总费用',
    total_kwh DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '总充电量',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY idx_user_date (user_id, bill_date)
) COMMENT='日账单主表';

-- 账单详情表
CREATE TABLE IF NOT EXISTS t_bill_detail (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bill_id INT NOT NULL COMMENT '关联的账单ID',
    session_id INT NOT NULL COMMENT '关联的充电会话ID',
    detail_number VARCHAR(50) NOT NULL COMMENT '详单编号',
    pile_code VARCHAR(10) NOT NULL COMMENT '充电桩编号',
    charged_kwh DECIMAL(10,2) NOT NULL COMMENT '充电电量',
    charging_time INT NOT NULL COMMENT '充电时长(分钟)',
    start_time TIMESTAMP NOT NULL COMMENT '启动时间',
    end_time TIMESTAMP NULL COMMENT '停止时间',
    charge_fee DECIMAL(10,2) NOT NULL COMMENT '充电费用',
    service_fee DECIMAL(10,2) NOT NULL COMMENT '服务费用',
    total_fee DECIMAL(10,2) NOT NULL COMMENT '总费用',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY idx_detail_number (detail_number),
    INDEX idx_bill_id (bill_id),
    INDEX idx_session_id (session_id)
) COMMENT='账单详情表';

-- 费率规则表
CREATE TABLE IF NOT EXISTS t_rate_rule (
    id INT AUTO_INCREMENT PRIMARY KEY,
    type ENUM('PEAK', 'NORMAL', 'VALLEY') NOT NULL COMMENT '费率类型：峰时、平时、谷时',
    price DECIMAL(10,2) NOT NULL COMMENT '电价(元/kWh)',
    start_time TIME NOT NULL COMMENT '开始时间',
    end_time TIME NOT NULL COMMENT '结束时间',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_type_time (type, start_time, end_time)
) COMMENT='费率规则表';

-- 服务费率表
CREATE TABLE IF NOT EXISTS t_service_rate (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rate DECIMAL(10,2) NOT NULL COMMENT '服务费率(元/kWh)',
    effective_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '生效时间',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_current TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否当前生效'
) COMMENT='服务费率表';

-- 队列日志表
CREATE TABLE IF NOT EXISTS t_queue_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL COMMENT '充电请求ID',
    from_status VARCHAR(20) NOT NULL COMMENT '变更前状态',
    to_status VARCHAR(20) NOT NULL COMMENT '变更后状态',
    pile_id INT NULL COMMENT '充电桩ID',
    queue_position INT NULL COMMENT '队列位置',
    log_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '日志时间',
    remark VARCHAR(255) NULL COMMENT '备注'
) COMMENT='队列变更日志表';

-- 故障日志表
CREATE TABLE IF NOT EXISTS t_fault_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pile_id INT NOT NULL COMMENT '充电桩ID',
    fault_time TIMESTAMP NOT NULL COMMENT '故障时间',
    recovery_time TIMESTAMP NULL COMMENT '恢复时间',
    status ENUM('ACTIVE', 'RESOLVED') NOT NULL DEFAULT 'ACTIVE' COMMENT '故障状态',
    description VARCHAR(255) NOT NULL COMMENT '故障描述',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT='故障日志表';

-- 报表数据表(日粒度)
CREATE TABLE IF NOT EXISTS t_report_daily (
    id INT AUTO_INCREMENT PRIMARY KEY,
    report_date DATE NOT NULL COMMENT '报表日期',
    pile_id INT NOT NULL COMMENT '充电桩ID',
    pile_code VARCHAR(10) NOT NULL COMMENT '充电桩编号',
    charge_count INT NOT NULL DEFAULT 0 COMMENT '充电次数',
    charge_time INT NOT NULL DEFAULT 0 COMMENT '充电总时长(分钟)',
    charge_kwh DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '充电总电量',
    charge_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '充电总费用',
    service_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '服务总费用',
    total_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '总费用',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY idx_date_pile (report_date, pile_id)
) COMMENT='日报表数据';

-- 系统配置表
CREATE TABLE IF NOT EXISTS t_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(50) NOT NULL COMMENT '配置键',
    config_value VARCHAR(255) NOT NULL COMMENT '配置值',
    description VARCHAR(255) NULL COMMENT '配置描述',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_config_key (config_key)
) COMMENT='系统配置表';

-- 用户表
CREATE TABLE IF NOT EXISTS t_user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL COMMENT '用户ID',
    username VARCHAR(50) NOT NULL COMMENT '用户名',
    password VARCHAR(255) NOT NULL COMMENT '密码',
    role ENUM('USER', 'ADMIN') NOT NULL DEFAULT 'USER' COMMENT '角色',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_user_id (user_id),
    UNIQUE KEY idx_username (username)
) COMMENT='用户表';

-- 初始化充电桩数据
INSERT INTO t_charge_pile (code, type, status, power) VALUES 
('A', 'FAST', 'OFFLINE', 30.00),
('B', 'FAST', 'OFFLINE', 30.00),
('C', 'SLOW', 'OFFLINE', 7.00),
('D', 'SLOW', 'OFFLINE', 7.00),
('E', 'SLOW', 'OFFLINE', 7.00);

-- 初始化费率规则
-- 峰时 (1.0元/度，10:00~15:00，18:00~21:00)
INSERT INTO t_rate_rule (type, price, start_time, end_time) VALUES 
('PEAK', 1.0, '10:00:00', '15:00:00'),
('PEAK', 1.0, '18:00:00', '21:00:00');

-- 平时 (0.7元/度，7:00~10:00，15:00~18:00，21:00~23:00)
INSERT INTO t_rate_rule (type, price, start_time, end_time) VALUES 
('NORMAL', 0.7, '07:00:00', '10:00:00'),
('NORMAL', 0.7, '15:00:00', '18:00:00'),
('NORMAL', 0.7, '21:00:00', '23:00:00');

-- 谷时 (0.4元/度，23:00~次日7:00)
INSERT INTO t_rate_rule (type, price, start_time, end_time) VALUES 
('VALLEY', 0.4, '23:00:00', '23:59:59'),
('VALLEY', 0.4, '00:00:00', '07:00:00');

-- 初始化服务费率
INSERT INTO t_service_rate (rate, is_current) VALUES (0.8, 1);

-- 初始化系统配置
INSERT INTO t_config (config_key, config_value, description) VALUES 
('FastChargingPileNum', '2', '快充桩数量'),
('TrickleChargingPileNum', '3', '慢充桩数量'),
('WaitingAreaSize', '6', '等候区车位容量'),
('ChargingQueueLen', '2', '每桩排队队列长度'),
('FastPower', '30', '单桩功率(快充) kWh/h'),
('SlowPower', '7', '单桩功率(慢充) kWh/h'),
('ServiceRate', '0.8', '服务费单价 元/kWh');

-- 初始化管理员账户
INSERT INTO t_user (user_id, username, password, role) VALUES 
('admin', 'admin', MD5('admin123'), 'ADMIN');

-- 初始化测试用户
INSERT INTO t_user (user_id, username, password, role) VALUES 
('user1', 'user1', MD5('user123'), 'USER'),
('user2', 'user2', MD5('user123'), 'USER'); 