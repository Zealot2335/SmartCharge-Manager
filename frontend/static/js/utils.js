/**
 * 智能充电桩调度计费系统 - 工具函数
 * 提供通用的辅助功能
 */

// 日期格式化
function formatDate(dateStr, format = 'YYYY-MM-DD') {
    const date = new Date(dateStr);
    
    if (isNaN(date.getTime())) {
        return '';
    }
    
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    
    return format
        .replace('YYYY', year)
        .replace('MM', month)
        .replace('DD', day)
        .replace('HH', hours)
        .replace('mm', minutes)
        .replace('ss', seconds);
}

// 金额格式化
function formatMoney(amount, decimals = 2) {
    if (typeof amount !== 'number') {
        return '0.00';
    }
    return amount.toFixed(decimals);
}

// 充电量格式化
function formatKwh(kwh, decimals = 2) {
    if (typeof kwh !== 'number') {
        return '0.00';
    }
    return `${kwh.toFixed(decimals)} kWh`;
}

// 时间格式化（分钟转为可读时间）
function formatMinutes(minutes) {
    if (typeof minutes !== 'number') {
        return '0分钟';
    }
    
    if (minutes < 60) {
        return `${Math.round(minutes)}分钟`;
    }
    
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = Math.round(minutes % 60);
    
    return `${hours}小时${remainingMinutes > 0 ? ` ${remainingMinutes}分钟` : ''}`;
}

// 获取充电模式显示文本
function getChargeModeName(mode) {
    const modeMap = {
        'FAST': '快充',
        'SLOW': '慢充'
    };
    return modeMap[mode] || mode;
}

// 获取请求状态显示文本
function getRequestStatusName(status) {
    const statusMap = {
        'WAITING': '等候中',
        'QUEUING': '排队中',
        'CHARGING': '充电中',
        'FINISHED': '已完成',
        'CANCELED': '已取消'
    };
    return statusMap[status] || status;
}

// 获取充电桩状态显示文本
function getPileStatusName(status) {
    const statusMap = {
        'AVAILABLE': '空闲',
        'BUSY': '忙碌',
        'FAULT': '故障',
        'OFFLINE': '离线'
    };
    return statusMap[status] || status;
}

// 获取费率类型显示文本
function getRateTypeName(type) {
    const typeMap = {
        'PEAK': '峰时',
        'NORMAL': '平时',
        'VALLEY': '谷时'
    };
    return typeMap[type] || type;
}

// 创建通知提示
function showNotification(message, type = 'info', duration = 3000) {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // 添加到页面
    const container = document.querySelector('.notification-container') || createNotificationContainer();
    container.appendChild(notification);
    
    // 显示动画
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    // 自动关闭
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, duration);
    
    return notification;
}

// 创建通知容器
function createNotificationContainer() {
    const container = document.createElement('div');
    container.className = 'notification-container';
    document.body.appendChild(container);
    return container;
}

// 检查授权并重定向
function checkAuth() {
    if (!API.auth.isLoggedIn()) {
        window.location.href = '/login.html';
        return false;
    }
    return true;
}

// 检查管理员权限并重定向
function checkAdmin() {
    if (!API.auth.isLoggedIn() || !API.auth.isAdmin()) {
        window.location.href = '/login.html';
        return false;
    }
    return true;
}

// 填充导航菜单
function setupNavigation() {
    const navbar = document.querySelector('.navbar-menu');
    if (!navbar) return;
    
    // 清空导航菜单
    navbar.innerHTML = '';
    
    // 是否已登录
    if (API.auth.isLoggedIn()) {
        // 添加导航项
        const isAdmin = API.auth.isAdmin();
        
        // 用户导航
        if (!isAdmin) {
            addNavItem(navbar, '首页', '/index.html');
            addNavItem(navbar, '充电请求', '/user/requests.html');
            addNavItem(navbar, '账单管理', '/user/bills.html');
        }
        
        // 管理员导航
        if (isAdmin) {
            addNavItem(navbar, '控制台', '/admin/index.html');
            addNavItem(navbar, '充电桩管理', '/admin/piles.html');
            addNavItem(navbar, '充电请求', '/admin/requests.html');
            addNavItem(navbar, '费率管理', '/admin/rates.html');
            addNavItem(navbar, '报表统计', '/admin/reports.html');
        }
        
        // 退出登录
        const logoutItem = document.createElement('li');
        const logoutLink = document.createElement('a');
        logoutLink.href = '#';
        logoutLink.textContent = '退出登录';
        logoutLink.addEventListener('click', (e) => {
            e.preventDefault();
            API.auth.logout();
            window.location.href = '/login.html';
        });
        logoutItem.appendChild(logoutLink);
        navbar.appendChild(logoutItem);
    } else {
        // 未登录导航
        addNavItem(navbar, '登录', '/login.html');
    }
    
    // 设置当前活动项
    highlightCurrentNavItem();
}

// 添加导航项
function addNavItem(navbar, text, href) {
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = href;
    link.textContent = text;
    item.appendChild(link);
    navbar.appendChild(item);
}

// 高亮当前导航项
function highlightCurrentNavItem() {
    const currentPath = window.location.pathname;
    
    // 获取所有导航链接
    const navLinks = document.querySelectorAll('.navbar-menu a');
    
    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

// 填充页脚
function setupFooter() {
    const footer = document.querySelector('.footer');
    if (!footer) return;
    
    footer.innerHTML = `
        <div class="container">
            <p>© ${new Date().getFullYear()} 智能充电桩调度计费系统 | 版本 1.0.0</p>
        </div>
    `;
}

// 创建元素并设置属性
function createElement(tag, attributes = {}, text = '') {
    const element = document.createElement(tag);
    
    // 设置属性
    for (const key in attributes) {
        element.setAttribute(key, attributes[key]);
    }
    
    // 设置文本
    if (text) {
        element.textContent = text;
    }
    
    return element;
}

// 创建状态标签
function createStatusLabel(status) {
    const label = createElement('span', { class: `status-label status-${status.toLowerCase()}` });
    label.textContent = getRequestStatusName(status);
    return label;
}

// 创建充电模式标签
function createModeLabel(mode) {
    const label = createElement('span', { class: `charge-mode charge-mode-${mode.toLowerCase()}` });
    label.textContent = getChargeModeName(mode);
    return label;
}

// 初始化页面
function initPage() {
    setupNavigation();
    setupFooter();
}

// 导出工具函数
const Utils = {
    formatDate,
    formatMoney,
    formatKwh,
    formatMinutes,
    getChargeModeName,
    getRequestStatusName,
    getPileStatusName,
    getRateTypeName,
    showNotification,
    checkAuth,
    checkAdmin,
    setupNavigation,
    setupFooter,
    createElement,
    createStatusLabel,
    createModeLabel,
    initPage
};

// 全局导出
window.Utils = Utils; 