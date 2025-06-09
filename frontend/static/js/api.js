/**
 * 智能充电桩调度计费系统 - API服务
 * 处理与后端API的所有交互
 */

const API_BASE_URL = 'http://localhost:8000/api';

// 存储用户Token
let authToken = localStorage.getItem('auth_token');
let userId = localStorage.getItem('user_id');
let userRole = localStorage.getItem('user_role');

/**
 * 构建请求头
 * @returns {Object} 包含授权令牌的请求头
 */
const getHeaders = () => {
    return {
        'Content-Type': 'application/json',
        'Authorization': authToken ? `Bearer ${authToken}` : '',
    };
};

/**
 * 通用请求方法
 * @param {string} endpoint - API端点
 * @param {string} method - 请求方法 (GET, POST, etc.)
 * @param {Object} data - 请求数据
 * @returns {Promise} 请求结果
 */
const request = async (endpoint, method = 'GET', data = null) => {
    const url = `${API_BASE_URL}${endpoint}`;
    const options = {
        method,
        headers: getHeaders(),
    };

    if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(url, options);
        
        // 检查Token是否过期
        if (response.status === 401) {
            // 清除本地存储的凭证
            logout();
            
            // 重定向到登录页面
            window.location.href = '/login.html';
            throw new Error('身份验证已过期，请重新登录');
        }
        
        // 解析响应
        if (response.headers.get('content-type')?.includes('application/json')) {
            const result = await response.json();
            
            // 检查API错误
            if (!response.ok) {
                throw new Error(result.detail || '请求失败');
            }
            
            return result;
        } else {
            const text = await response.text();
            
            // 检查API错误
            if (!response.ok) {
                throw new Error(text || '请求失败');
            }
            
            return text;
        }
    } catch (error) {
        console.error('API请求错误:', error);
        throw error;
    }
};

/**
 * 认证相关API
 */
const auth = {
    /**
     * 用户登录
     * @param {string} username - 用户名
     * @param {string} password - 密码
     * @returns {Promise} 登录结果
     */
    login: async (username, password) => {
        // --- 修复开始 ---
        // 后端 OAuth2PasswordRequestForm 需要 application/x-www-form-urlencoded 格式
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData,
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || '登录失败');
        }

        const result = await response.json();
        // --- 修复结束 ---
        
        // 存储token和用户信息
        if (result.access_token) {
            authToken = result.access_token;
            userId = result.user_id;
            userRole = result.role;
            
            localStorage.setItem('auth_token', result.access_token);
            localStorage.setItem('user_id', result.user_id);
            localStorage.setItem('user_role', result.role);
        }
        
        return result;
    },
    
    /**
     * 用户注册
     * @param {Object} userData - 用户数据
     * @returns {Promise} 注册结果
     */
    register: (userData) => {
        return request('/auth/register', 'POST', userData);
    },
    
    /**
     * 获取当前用户信息
     * @returns {Promise} 用户信息
     */
    getCurrentUser: () => {
        return request('/auth/me', 'GET');
    },
    
    /**
     * 检查是否已登录
     * @returns {boolean} 是否已登录
     */
    isLoggedIn: () => {
        return !!authToken;
    },
    
    /**
     * 获取用户角色
     * @returns {string} 用户角色
     */
    getUserRole: () => {
        return localStorage.getItem('user_role');
    },
    
    /**
     * 是否是管理员
     * @returns {boolean} 是否是管理员
     */
    isAdmin: () => {
        return localStorage.getItem('user_role') === 'ADMIN';
    }
};

/**
 * 充电请求相关API
 */
const charging = {
    /**
     * 创建充电请求
     * @param {Object} requestData - 充电请求数据
     * @returns {Promise} 创建结果
     */
    createRequest: (requestData) => {
        return request('/charging/request', 'POST', requestData);
    },
    
    /**
     * 获取用户的所有充电请求
     * @param {string} status - 可选，按状态筛选
     * @returns {Promise} 充电请求列表
     */
    getUserRequests: (status = null) => {
        const endpoint = status ? `/charging/requests?status=${status}` : '/charging/requests';
        return request(endpoint, 'GET');
    },
    
    /**
     * 获取充电请求详情
     * @param {number} requestId - 请求ID
     * @returns {Promise} 请求详情
     */
    getRequestDetails: (requestId) => {
        return request(`/charging/${requestId}`, 'GET');
    },
    
    /**
     * 获取充电状态
     * @param {number} requestId - 请求ID
     * @returns {Promise} 充电状态
     */
    getChargeState: (requestId) => {
        return request(`/charging/${requestId}/state`, 'GET');
    },
    
    /**
     * 更新充电请求
     * @param {number} requestId - 请求ID
     * @param {Object} updateData - 更新数据
     * @returns {Promise} 更新结果
     */
    updateRequest: (requestId, updateData) => {
        return request(`/charging/${requestId}`, 'PATCH', updateData);
    },
    
    /**
     * 取消充电请求
     * @param {number} requestId - 请求ID
     * @returns {Promise} 取消结果
     */
    cancelRequest: (requestId) => {
        return request(`/charging/${requestId}`, 'DELETE');
    },
    
    /**
     * 修改充电模式
     * @param {number} requestId - 请求ID
     * @param {string} newMode - 新的充电模式 (FAST/SLOW)
     * @returns {Promise} 更新后的请求对象
     */
    changeChargeMode: (requestId, newMode) => {
        return request(`/charging/requests/${requestId}/mode`, 'PUT', { mode: newMode });
    },
    
    /**
     * 修改充电量
     * @param {number} requestId - 请求ID
     * @param {number} newAmount - 新的充电量 (kWh)
     * @returns {Promise} 更新后的请求对象
     */
    changeChargeAmount: (requestId, newAmount) => {
        return request(`/charging/requests/${requestId}/amount`, 'PATCH', { amount_kwh: newAmount });
    },
    
    /**
     * 获取队列信息
     * @param {string} mode - 充电模式 (FAST/SLOW)
     * @returns {Promise} 队列信息
     */
    getQueueInfo: (mode) => {
        return request(`/charging/queue/${mode}`, 'GET');
    },
    
    /**
     * 获取等候区状态
     * @returns {Promise<any>}
     */
    getWaitingAreaStatus: async () => {
        return await request('/charging/waiting_area');
    },
    
    /**
     * 模拟充电进度（仅测试用）
     * @param {number} requestId - 请求ID
     * @param {number} progress - 进度百分比
     * @returns {Promise} 模拟结果
     */
    simulateCharging: (requestId, progress) => {
        return request(`/charging/${requestId}/simulate?progress=${progress}`, 'POST');
    }
};

/**
 * 账单相关API
 */
const billing = {
    /**
     * 获取日账单
     * @param {string} date - 日期 (YYYY-MM-DD)
     * @returns {Promise} 账单数据
     */
    getDailyBill: (date) => {
        return request(`/billing/daily/${date}`, 'GET');
    },
    
    /**
     * 获取账单详情
     * @param {number} sessionId - 会话ID
     * @returns {Promise} 账单详情
     */
    getBillDetails: (sessionId) => {
        console.log(`Getting bill details for session ID: ${sessionId}`);
        return request(`/billing/bills/${sessionId}`, 'GET');
    },
    
    /**
     * 获取详单信息
     * @param {string} detailNumber - 详单编号
     * @returns {Promise} 详单信息
     */
    getDetailByNumber: (detailNumber) => {
        return request(`/billing/details/${detailNumber}`, 'GET');
    }
};

/**
 * 管理员相关API
 */
const admin = {
    /**
     * 获取充电桩列表
     * @returns {Promise} 充电桩列表
     */
    getPiles: () => {
        return request('/admin/pile', 'GET');
    },
    
    /**
     * 启动充电桩
     * @param {string} pileCode - 充电桩编号
     * @returns {Promise} 更新结果
     */
    powerOnPile: (pileCode) => {
        return request(`/admin/pile/${pileCode}/poweron`, 'POST');
    },
    
    /**
     * 关闭充电桩
     * @param {string} pileCode - 充电桩编号
     * @returns {Promise} 更新结果
     */
    shutdownPile: (pileCode) => {
        return request(`/admin/pile/${pileCode}/shutdown`, 'POST');
    },
    
    /**
     * 获取所有充电请求
     * @param {Object} filters - 筛选条件
     * @returns {Promise} 充电请求列表
     */
    getAllRequests: (filters = {}) => {
        let endpoint = '/admin/requests';
        const params = new URLSearchParams();
        
        for (const key in filters) {
            if (filters[key]) {
                params.append(key, filters[key]);
            }
        }
        
        if (params.toString()) {
            endpoint += `?${params.toString()}`;
        }
        
        return request(endpoint, 'GET');
    },
    
    /**
     * 获取费率规则
     * @returns {Promise} 费率规则列表
     */
    getRates: () => {
        return request('/admin/rates', 'GET');
    },
    
    /**
     * 更新费率规则
     * @param {number} rateId - 费率规则ID
     * @param {Object} updateData - 更新数据
     * @returns {Promise} 更新结果
     */
    updateRate: (rateId, updateData) => {
        return request(`/admin/rates/${rateId}`, 'PATCH', updateData);
    },
    
    /**
     * 获取服务费率
     * @returns {Promise} 服务费率
     */
    getServiceRate: () => {
        return request('/admin/service-rate', 'GET');
    },
    
    /**
     * 更新服务费率
     * @param {Object} updateData - 更新数据
     * @returns {Promise} 更新结果
     */
    updateServiceRate: (updateData) => {
        return request('/admin/service-rate', 'PATCH', updateData);
    },
    
    /**
     * 获取日报表
     * @param {string} date - 日期 (YYYY-MM-DD)
     * @returns {Promise} 报表数据
     */
    getDailyReport: (date) => {
        return request(`/admin/reports/daily/${date}`, 'GET');
    },
    
    /**
     * 获取故障日志
     * @returns {Promise} 故障日志列表
     */
    getFaultLogs: () => {
        return request('/admin/faults', 'GET');
    },
    
    /**
     * 报告故障
     * @param {Object} faultData - 故障数据
     * @returns {Promise} 报告结果
     */
    reportFault: (faultData) => {
        return request('/admin/faults', 'POST', faultData);
    },
    
    /**
     * 故障恢复
     * @param {number} faultId - 故障ID
     * @returns {Promise} 恢复结果
     */
    resolveFault: (faultId) => {
        return request(`/admin/faults/${faultId}/resolve`, 'POST');
    },
};

/**
 * 退出登录
 */
function logout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_role');
    authToken = null;
    userId = null;
    userRole = null;
}

// 导出API服务
const API = {
    auth,
    charging,
    billing,
    admin,
    logout
};

// 全局导出
window.API = API; 