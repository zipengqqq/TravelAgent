/**
 * TravelAssistant 应用逻辑
 * 处理用户界面交互和消息处理
 */

class ChatApp {
    constructor() {
        this.messagesContainer = document.getElementById('messagesContainer');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.typingIndicator = document.getElementById('typingIndicator');

        this.isTyping = false;
        this.welcomeShown = true;

        this.init();
    }

    init() {
        // 绑定事件
        this.messageInput.addEventListener('input', () => this.handleInput());
        this.messageInput.addEventListener('keydown', (e) => this.handleKeyDown(e));
        this.sendButton.addEventListener('click', () => this.sendMessage());

        // 自动调整输入框高度
        this.messageInput.addEventListener('input', () => this.autoResizeInput());
    }

    /**
     * 处理输入变化
     */
    handleInput() {
        const message = this.messageInput.value.trim();
        this.sendButton.disabled = !message || this.isTyping;
    }

    /**
     * 处理键盘事件
     */
    handleKeyDown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!this.sendButton.disabled) {
                this.sendMessage();
            }
        }
    }

    /**
     * 自动调整输入框高度
     */
    autoResizeInput() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 150) + 'px';
    }

    /**
     * 发送消息
     */
    async sendMessage() {
        const message = this.messageInput.value.trim();

        if (!message || this.isTyping) {
            return;
        }

        // 隐藏欢迎消息
        if (this.welcomeShown) {
            const welcomeMessage = this.messagesContainer.querySelector('.welcome-message');
            if (welcomeMessage) {
                welcomeMessage.remove();
            }
            this.welcomeShown = false;
        }

        // 清空输入框
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        this.sendButton.disabled = true;

        // 显示用户消息
        this.addMessage(message, 'user');
        this.isTyping = true;

        // 显示打字指示器
        this.showTypingIndicator();

        try {
            // 调用 API
            const response = await api.chat(message);

            // 隐藏打字指示器
            this.hideTypingIndicator();

            // 显示 AI 回复
            this.addMessage(response.response, 'assistant');
        } catch (error) {
            // 隐藏打字指示器
            this.hideTypingIndicator();

            // 显示错误消息
            this.addErrorMessage(error.message || '发送消息时出错');
        } finally {
            this.isTyping = false;
            this.handleInput();
        }
    }

    /**
     * 添加消息到界面
     */
    addMessage(content, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = type === 'user' ? '👤' : '🤖';

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = this.formatMessage(content);

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(messageContent);

        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();

        // 触发动画
        setTimeout(() => {
            messageDiv.style.animation = 'none';
            messageDiv.offsetHeight; // 触发重排
            messageDiv.style.animation = 'slideIn 0.3s ease-out';
        }, 10);
    }

    /**
     * 添加错误消息
     */
    addErrorMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = '⚠️';

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = `<em>${this.escapeHtml(content)}</em>`;

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(messageContent);

        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    /**
     * 格式化消息内容（支持基本的 Markdown）
     */
    formatMessage(content) {
        // 转义 HTML
        let formatted = this.escapeHtml(content);

        // 粗体
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // 斜体
        formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');

        // 代码块
        formatted = formatted.replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

        // 行内代码
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

        // 标题
        formatted = formatted.replace(/^### (.*$)/gm, '<h3>$1</h3>');
        formatted = formatted.replace(/^## (.*$)/gm, '<h2>$1</h2>');
        formatted = formatted.replace(/^# (.*$)/gm, '<h1>$1</h1>');

        // 列表
        formatted = formatted.replace(/^\- (.*$)/gm, '<li>$1</li>');
        formatted = formatted.replace(/^(\d+)\. (.*$)/gm, '<li>$2</li>');

        // 换行
        formatted = formatted.replace(/\n\n/g, '</p><p>');
        formatted = formatted.replace(/\n/g, '<br>');

        return `<p>${formatted}</p>`;
    }

    /**
     * 转义 HTML 特殊字符
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * 显示打字指示器
     */
    showTypingIndicator() {
        this.typingIndicator.style.display = 'block';
    }

    /**
     * 隐藏打字指示器
     */
    hideTypingIndicator() {
        this.typingIndicator.style.display = 'none';
    }

    /**
     * 滚动到底部
     */
    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});
