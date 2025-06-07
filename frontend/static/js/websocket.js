/**
 * 智能充电桩调度计费系统 - WebSocket客户端
 * 处理与服务器的实时通信
 */

class WebSocketClient {
    /**
     * 构造函数
     * @param {string} baseUrl - WebSocket服务器基础URL
     */
    constructor(baseUrl = 'ws://localhost:8000') {
        this.baseUrl = baseUrl;
        this.socket = null;
        this.connected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000; // 重连延迟(毫秒)
        this.eventHandlers = {};
        this.messageQueue = [];
        this.clientId = this.generateClientId();
    }
    
    /**
     * 生成客户端ID
     * @returns {string} 客户端ID
     */
    generateClientId() {
        return 'client_' + Math.random().toString(36).substr(2, 9);
    }
    
    /**
     * 连接到用户WebSocket
     * @param {string} userId - 用户ID
     * @returns {Promise} 连接结果
     */
    connectUser(userId) {
        if (!userId) {
            return Promise.reject(new Error('用户ID不能为空'));
        }
        
        return this.connect(`/ws/user/${userId}/${this.clientId}`);
    }
    
    /**
     * 连接到管理员WebSocket
     * @returns {Promise} 连接结果
     */
    connectAdmin() {
        return this.connect(`/ws/admin/${this.clientId}`);
    }
    
    /**
     * 连接WebSocket
     * @param {string} path - WebSocket路径
     * @returns {Promise} 连接结果
     */
    connect(path) {
        return new Promise((resolve, reject) => {
            try {
                // 关闭现有连接
                this.disconnect();
                
                // 创建新连接
                const wsUrl = `${this.baseUrl}${path}`;
                this.socket = new WebSocket(wsUrl);
                
                // 连接打开
                this.socket.onopen = () => {
                    this.connected = true;
                    this.reconnectAttempts = 0;
                    console.log('WebSocket连接已建立');
                    
                    // 发送队列中的消息
                    this.flushMessageQueue();
                    
                    // 触发已连接事件
                    this.trigger('connected');
                    
                    resolve();
                };
                
                // 接收消息
                this.socket.onmessage = (event) => {
                    try {
                        const message = JSON.parse(event.data);
                        this.handleMessage(message);
                    } catch (error) {
                        console.error('解析WebSocket消息失败:', error);
                    }
                };
                
                // 连接关闭
                this.socket.onclose = () => {
                    this.connected = false;
                    console.log('WebSocket连接已关闭');
                    
                    // 触发断开连接事件
                    this.trigger('disconnected');
                    
                    // 尝试重新连接
                    this.attemptReconnect(path);
                };
                
                // 连接错误
                this.socket.onerror = (error) => {
                    console.error('WebSocket连接错误:', error);
                    reject(error);
                };
            } catch (error) {
                console.error('创建WebSocket连接失败:', error);
                reject(error);
            }
        });
    }
    
    /**
     * 断开连接
     */
    disconnect() {
        if (this.socket) {
            this.socket.close();
            this.socket = null;
            this.connected = false;
        }
    }
    
    /**
     * 尝试重新连接
     * @param {string} path - WebSocket路径
     */
    attemptReconnect(path) {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('达到最大重连次数，不再尝试重连');
            return;
        }
        
        this.reconnectAttempts++;
        console.log(`尝试重新连接 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
        
        setTimeout(() => {
            this.connect(path).catch(error => {
                console.error('重新连接失败:', error);
            });
        }, this.reconnectDelay * this.reconnectAttempts);
    }
    
    /**
     * 发送消息
     * @param {Object} message - 要发送的消息
     */
    send(message) {
        if (!this.connected) {
            // 连接未建立，加入队列
            this.messageQueue.push(message);
            return;
        }
        
        try {
            this.socket.send(JSON.stringify(message));
        } catch (error) {
            console.error('发送WebSocket消息失败:', error);
            // 加入队列，等待重连后发送
            this.messageQueue.push(message);
        }
    }
    
    /**
     * 发送队列中的消息
     */
    flushMessageQueue() {
        if (!this.connected || this.messageQueue.length === 0) {
            return;
        }
        
        console.log(`发送队列中的${this.messageQueue.length}条消息`);
        
        while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            try {
                this.socket.send(JSON.stringify(message));
            } catch (error) {
                console.error('发送队列消息失败:', error);
                // 放回队列头部，下次再试
                this.messageQueue.unshift(message);
                break;
            }
        }
    }
    
    /**
     * 处理接收到的消息
     * @param {Object} message - 接收到的消息
     */
    handleMessage(message) {
        // 提取消息类型
        const type = message.type;
        if (!type) {
            console.warn('收到无类型的WebSocket消息:', message);
            return;
        }
        
        // 触发对应事件
        this.trigger(type, message);
        
        // 触发通用消息事件
        this.trigger('message', message);
    }
    
    /**
     * 注册事件处理器
     * @param {string} event - 事件名称
     * @param {Function} handler - 事件处理函数
     */
    on(event, handler) {
        if (!this.eventHandlers[event]) {
            this.eventHandlers[event] = [];
        }
        this.eventHandlers[event].push(handler);
        
        return this; // 支持链式调用
    }
    
    /**
     * 移除事件处理器
     * @param {string} event - 事件名称
     * @param {Function} handler - 要移除的处理函数，不指定则移除所有
     */
    off(event, handler) {
        if (!this.eventHandlers[event]) {
            return this;
        }
        
        if (!handler) {
            // 移除所有处理器
            delete this.eventHandlers[event];
        } else {
            // 移除特定处理器
            this.eventHandlers[event] = this.eventHandlers[event].filter(h => h !== handler);
        }
        
        return this; // 支持链式调用
    }
    
    /**
     * 触发事件
     * @param {string} event - 事件名称
     * @param {any} data - 事件数据
     */
    trigger(event, data) {
        const handlers = this.eventHandlers[event];
        if (handlers) {
            handlers.forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`执行事件处理器出错 (${event}):`, error);
                }
            });
        }
    }
}

// 创建WebSocket客户端实例
const wsClient = new WebSocketClient();

// 如果用户已登录，自动连接
if (API && API.auth && API.auth.isLoggedIn()) {
    const userId = localStorage.getItem('user_id');
    const userRole = localStorage.getItem('user_role');
    
    if (userId) {
        if (userRole === 'ADMIN') {
            wsClient.connectAdmin().catch(error => {
                console.error('管理员WebSocket连接失败:', error);
            });
        } else {
            wsClient.connectUser(userId).catch(error => {
                console.error('用户WebSocket连接失败:', error);
            });
        }
    }
}

// 全局导出
window.wsClient = wsClient; 