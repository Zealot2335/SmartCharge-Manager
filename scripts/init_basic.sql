-- Create database
CREATE DATABASE IF NOT EXISTS smart_charge DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE smart_charge;

-- Charging pile table
CREATE TABLE IF NOT EXISTS t_charge_pile (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(10) NOT NULL,
    type ENUM('FAST', 'SLOW') NOT NULL,
    status ENUM('AVAILABLE', 'BUSY', 'FAULT', 'OFFLINE') NOT NULL DEFAULT 'OFFLINE',
    power DECIMAL(10,2) NOT NULL,
    total_charge_count INT NOT NULL DEFAULT 0,
    total_charge_time INT NOT NULL DEFAULT 0,
    total_charge_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_pile_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Charging request table
CREATE TABLE IF NOT EXISTS t_car_request (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    queue_number VARCHAR(20) NOT NULL,
    mode ENUM('FAST', 'SLOW') NOT NULL,
    amount_kwh DECIMAL(10,2) NOT NULL,
    battery_capacity DECIMAL(10,2) NOT NULL,
    status ENUM('WAITING', 'QUEUING', 'CHARGING', 'FINISHED', 'CANCELED') NOT NULL DEFAULT 'WAITING',
    pile_id INT NULL,
    queue_position INT NULL,
    request_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    start_time TIMESTAMP NULL,
    end_time TIMESTAMP NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_queue_number (queue_number),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_pile_id (pile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Charging session table
CREATE TABLE IF NOT EXISTS t_charge_session (
    id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL,
    pile_id INT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NULL,
    charged_kwh DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    charging_time INT NOT NULL DEFAULT 0,
    charge_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    service_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    status ENUM('CHARGING', 'COMPLETED', 'INTERRUPTED') NOT NULL DEFAULT 'CHARGING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_request_id (request_id),
    INDEX idx_pile_id (pile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Bill master table
CREATE TABLE IF NOT EXISTS t_bill_master (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    bill_date DATE NOT NULL,
    total_charge_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_service_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_kwh DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY idx_user_date (user_id, bill_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Bill detail table
CREATE TABLE IF NOT EXISTS t_bill_detail (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bill_id INT NOT NULL,
    session_id INT NOT NULL,
    detail_number VARCHAR(50) NOT NULL,
    pile_code VARCHAR(10) NOT NULL,
    charged_kwh DECIMAL(10,2) NOT NULL,
    charging_time INT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NULL,
    charge_fee DECIMAL(10,2) NOT NULL,
    service_fee DECIMAL(10,2) NOT NULL,
    total_fee DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY idx_detail_number (detail_number),
    INDEX idx_bill_id (bill_id),
    INDEX idx_session_id (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Rate rule table
CREATE TABLE IF NOT EXISTS t_rate_rule (
    id INT AUTO_INCREMENT PRIMARY KEY,
    type ENUM('PEAK', 'NORMAL', 'VALLEY') NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_type_time (type, start_time, end_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Service rate table
CREATE TABLE IF NOT EXISTS t_service_rate (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rate DECIMAL(10,2) NOT NULL,
    effective_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_current TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- User table
CREATE TABLE IF NOT EXISTS t_user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('USER', 'ADMIN') NOT NULL DEFAULT 'USER',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_user_id (user_id),
    UNIQUE KEY idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Initialize charging piles
INSERT IGNORE INTO t_charge_pile (code, type, status, power) VALUES 
('A', 'FAST', 'AVAILABLE', 30.00),
('B', 'FAST', 'AVAILABLE', 30.00),
('C', 'SLOW', 'AVAILABLE', 7.00),
('D', 'SLOW', 'AVAILABLE', 7.00),
('E', 'SLOW', 'AVAILABLE', 7.00);

-- Initialize rate rules
INSERT IGNORE INTO t_rate_rule (type, price, start_time, end_time) VALUES 
('PEAK', 1.0, '10:00:00', '15:00:00'),
('PEAK', 1.0, '18:00:00', '21:00:00'),
('NORMAL', 0.7, '07:00:00', '10:00:00'),
('NORMAL', 0.7, '15:00:00', '18:00:00'),
('NORMAL', 0.7, '21:00:00', '23:00:00'),
('VALLEY', 0.4, '23:00:00', '23:59:59'),
('VALLEY', 0.4, '00:00:00', '07:00:00');

-- Initialize service rate
INSERT IGNORE INTO t_service_rate (rate, is_current) VALUES (0.8, 1);

-- Initialize users
INSERT IGNORE INTO t_user (user_id, username, password, role) VALUES 
('admin', 'admin', 'admin', 'ADMIN'),
('user', 'user', 'admin', 'USER'); 