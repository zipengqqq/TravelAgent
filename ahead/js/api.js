/**
 * TravelAgent API 客户端
 * 提供与后端 API 的交互方法
 */

class TravelAgentAPI {
    /**
     * 创建 API 客户端实例
     * @param {string} baseURL - API 基础 URL，默认为当前域名
     */
    constructor(baseURL) {
        const hasWindowOrigin =
            typeof window !== 'undefined' &&
            window.location &&
            typeof window.location.origin === 'string' &&
            window.location.origin.startsWith('http');

        const windowOrigin = hasWindowOrigin ? window.location.origin : '';
        const isLocalhost =
            typeof window !== 'undefined' &&
            window.location &&
            (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

        const preferBackendOrigin =
            isLocalhost && typeof window !== 'undefined' && window.location && window.location.port && window.location.port !== '8288';

        const origin = preferBackendOrigin ? 'http://localhost:8288' : (windowOrigin || 'http://localhost:8288');
        const resolved = baseURL || `${origin}/api/v1`;
        this.baseURL = resolved.replace(/\/+$/, '');
        // 固定的 user_id
        this.user_id = 1;
        this.thread_id = "1";
    }

    async post(path, body) {
        const url = `${this.baseURL}${path}`;
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {})
        });

        if (!response.ok) {
            const errorText = await response.text();
            if (response.status === 404) {
                throw new Error(`接口不存在(404): ${response.url || url}`);
            }
            try {
                const errorData = JSON.parse(errorText);
                throw new Error(errorData.detail || errorData.error || errorData.message || `请求失败(${response.status}): ${response.url || url}`);
            } catch {
                throw new Error(`请求失败(${response.status}): ${response.url || url}\n${errorText}`);
            }
        }

        return response.json();
    }

    /**
     * 发送聊天请求（非流式）
     * @param {string} message - 用户消息
     * @returns {Promise<Object>} 响应数据
     */
    async chat(message, threadId) {
        return await new Promise((resolve, reject) => {
            let latest = '';
            this.chatStream(
                message,
                (chunk) => {
                    if (chunk?.type === 'chunk' && chunk?.data?.response != null) {
                        latest = String(chunk.data.response);
                    }
                },
                () => resolve({ response: latest }),
                (error) => reject(error),
                threadId
            );
        });
    }

    async conversationList() {
        return await this.post('/conversation/list', { user_id: this.user_id });
    }

    async conversationAdd() {
        return await this.post('/conversation/add', { user_id: this.user_id });
    }

    async conversationSelect(threadId) {
        return await this.post('/conversation/select', { thread_id: threadId });
    }

    /**
     * 流式聊天
     * @param {string} message - 用户消息
     * @param {Function} onChunk - 接收数据块的回调函数 (chunk: {type: string, data: object})
     * @param {Function} onComplete - 完成回调函数
     * @param {Function} onError - 错误回调函数
     * @param {string} threadId - 可选的会话 thread_id
     */
    async chatStream(message, onChunk, onComplete, onError, threadId) {
        try {
            const url = `${this.baseURL}/chat`;
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: this.user_id,
                    question: message,
                    thread_id: threadId ?? this.thread_id
                })
            });

            if (!response.ok) {
                const errorText = await response.text();
                if (response.status === 404) {
                    throw new Error(`接口不存在(404): ${response.url || url}`);
                }
                try {
                    const errorData = JSON.parse(errorText);
                    throw new Error(errorData.detail || errorData.error || errorData.message || `请求失败(${response.status}): ${response.url || url}`);
                } catch {
                    throw new Error(`请求失败(${response.status}): ${response.url || url}\n${errorText}`);
                }
            }

            // 使用 ReadableStream 读取 SSE 数据
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                // 解码并添加到缓冲区
                buffer += decoder.decode(value, { stream: true });

                // 处理缓冲区中的每一行
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // 保留最后一个不完整的行

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6).trim();
                        if (data) {
                            try {
                                const chunk = JSON.parse(data);
                                onChunk(chunk);

                                if (chunk.type === 'end') {
                                    onComplete();
                                    return;
                                }
                            } catch (e) {
                                console.error('解析 SSE 数据失败:', e, data);
                            }
                        }
                    }
                }
            }
        } catch (error) {
            console.error('API 错误:', error);
            onError(error);
        }
    }
}

// 创建全局 API 实例
const api = new TravelAgentAPI();
