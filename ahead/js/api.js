/**
 * TravelAgent API 客户端
 * 提供与后端 API 的交互方法
 */

class TravelAgentAPI {
    /**
     * 创建 API 客户端实例
     * @param {string} baseURL - API 基础 URL，默认为当前域名
     */
    constructor(baseURL = 'http://localhost:8288') {
        this.baseURL = baseURL;
        // 固定的 user_id 和 thread_id
        this.user_id = 1;
        this.thread_id = "1";
    }

    /**
     * 发送聊天请求（非流式）
     * @param {string} message - 用户消息
     * @returns {Promise<Object>} 响应数据
     */
    async chat(message) {
        try {
            const response = await fetch(`${this.baseURL}/api/v1/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: this.user_id,
                    question: message,
                    thread_id: this.thread_id
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || errorData.error || '请求失败');
            }

            const data = await response.json();
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
            const response = await fetch(`${this.baseURL}/api/v1/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: this.user_id,
                    question: message,
                    thread_id: this.thread_id
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || errorData.error || '请求失败');
            }

            const data = await response.json();
            onChunk(data.response || '');
            onComplete();
        } catch (error) {
            console.error('API 错误:', error);
            onError(error);
        }
    }
}

// 创建全局 API 实例
const api = new TravelAgentAPI();
