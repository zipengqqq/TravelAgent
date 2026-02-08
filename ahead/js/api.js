/**
 * TravelAgent API 客户端
 * 提供与后端 API 的交互方法
 */

class TravelAgentAPI {
    /**
     * 创建 API 客户端实例
     * @param {string} baseURL - API 基础 URL，默认为当前域名
     */
    constructor(baseURL = '') {
        this.baseURL = baseURL;
        this.user_id = this.getUserId();
        this.thread_id = this.getThreadId();
    }

    /**
     * 获取或生成用户 ID
     * @returns {number} 用户 ID
     */
    getUserId() {
        let userId = localStorage.getItem('travelAgent_userId');
        if (!userId) {
            userId = Math.floor(Math.random() * 1000000);
            localStorage.setItem('travelAgent_userId', userId);
        }
        return parseInt(userId);
    }

    /**
     * 获取当前线程 ID
     * @returns {string} 线程 ID
     */
    getThreadId() {
        return localStorage.getItem('travelAgent_threadId') || '';
    }

    /**
     * 保存线程 ID
     * @param {string} threadId - 线程 ID
     */
    saveThreadId(threadId) {
        if (threadId) {
            localStorage.setItem('travelAgent_threadId', threadId);
            this.thread_id = threadId;
        }
    }

    /**
     * 清除线程 ID（开始新对话）
     */
    clearThreadId() {
        localStorage.removeItem('travelAgent_threadId');
        this.thread_id = '';
    }

    /**
     * 发送聊天请求（非流式）
     * @param {string} message - 用户消息
     * @returns {Promise<Object>} 响应数据
     */
    async chat(message) {
        try {
            const response = await fetch(`${this.baseURL}/api/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: this.user_id,
                    question: message,
                    thread_id: this.thread_id || null
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || errorData.error || '请求失败');
            }

            const data = await response.json();

            // 保存线程 ID 以便后续对话
            this.saveThreadId(data.thread_id);

            return data;
        } catch (error) {
            console.error('API 错误:', error);
            throw error;
        }
    }

    /**
     * 流式聊天（可选实现）
     * @param {string} message - 用户消息
     * @param {Function} onChunk - 接收数据块的回调函数
     * @param {Function} onComplete - 完成回调函数
     * @param {Function} onError - 错误回调函数
     */
    async chatStream(message, onChunk, onComplete, onError) {
        try {
            const response = await fetch(`${this.baseURL}/api/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: this.user_id,
                    question: message,
                    thread_id: this.thread_id || null
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || errorData.error || '请求失败');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();

                if (done) {
                    onComplete();
                    break;
                }

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data === '[DONE]') {
                            onComplete();
                            return;
                        }

                        try {
                            const parsed = JSON.parse(data);
                            if (parsed.thread_id) {
                                this.saveThreadId(parsed.thread_id);
                            }
                            if (parsed.content || parsed.response) {
                                onChunk(parsed.content || parsed.response);
                            }
                        } catch (e) {
                            console.warn('解析 SSE 数据失败:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('流式 API 错误:', error);
            onError(error);
        }
    }

    /**
     * 健康检查
     * @returns {Promise<Object>} 健康状态
     */
    async healthCheck() {
        try {
            const response = await fetch(`${this.baseURL}/health`);
            if (!response.ok) {
                throw new Error('健康检查失败');
            }
            return await response.json();
        } catch (error) {
            console.error('健康检查错误:', error);
            throw error;
        }
    }
}

// 创建全局 API 实例
const api = new TravelAgentAPI();
