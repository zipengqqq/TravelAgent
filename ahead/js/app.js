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
        this.chatList = document.getElementById('chatList');
        this.newChatButton = document.getElementById('newChatButton');
        this.sidebar = document.getElementById('sidebar');
        this.sidebarToggle = document.getElementById('sidebarToggle');
        this.sidebarClose = document.getElementById('sidebarClose');
        this.sidebarBackdrop = document.getElementById('sidebarBackdrop');

        this.isTyping = false;
        this.welcomeShown = true;
        this.conversations = [];
        this.activeConversationId = null;
        this.welcomeTemplate = '';

        this.init();
    }

    init() {
        this.messageInput.addEventListener('input', () => this.handleInput());
        this.messageInput.addEventListener('keydown', (e) => this.handleKeyDown(e));
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('input', () => this.autoResizeInput());

        this.newChatButton.addEventListener('click', () => {
            this.createNewConversation(true).catch((e) => this.addErrorMessage(e.message || '创建对话失败'));
        });
        this.sidebarToggle.addEventListener('click', () => this.openSidebar());
        this.sidebarClose.addEventListener('click', () => this.closeSidebar());
        this.sidebarBackdrop.addEventListener('click', () => this.closeSidebar());

        this.welcomeTemplate = this.messagesContainer.querySelector('.welcome-message')?.outerHTML || '';
        this.bootstrap().catch((e) => this.addErrorMessage(e.message || '加载对话失败'));
    }

    async bootstrap() {
        await this.refreshConversationList();
        if (this.conversations.length === 0) {
            const conversation = await this.createNewConversation(false);
            this.activeConversationId = conversation.id;
            this.renderChatList();
            this.renderMessages([]);
            return;
        }

        this.activeConversationId = this.conversations[0].id;
        this.renderChatList();
        await this.loadAndRenderActiveConversation();
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

        let conversation = this.getActiveConversation();
        if (!conversation) {
            conversation = await this.createNewConversation(false);
            this.activeConversationId = conversation.id;
            this.renderChatList();
        }

        if (this.welcomeShown) {
            const welcomeMessage = this.messagesContainer.querySelector('.welcome-message');
            if (welcomeMessage) welcomeMessage.remove();
            this.welcomeShown = false;
        }

        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        this.sendButton.disabled = true;

        if (!conversation.title || conversation.title === conversation.threadId || conversation.title === '新对话') {
            conversation.title = this.makeTitleFromMessage(message);
        }
        conversation.updatedAt = Date.now();
        this.renderChatList();

        this.addMessage(message, 'user');
        this.isTyping = true;

        this.showTypingIndicator();

        try {
            const assistantMessageDiv = this.addMessage('', 'assistant');
            const assistantContentEl = assistantMessageDiv.querySelector('.message-content');
            let assistantText = '';
            let receivedFirstChunk = false;

            await api.chatStream(
                message,
                (chunk) => {
                    if (chunk.type === 'node') {
                        console.log('Node:', chunk.node, chunk.data);
                    } else if (chunk.type === 'chunk') {
                        if (chunk.data.response) {
                            if (!receivedFirstChunk) {
                                this.hideTypingIndicator();
                                receivedFirstChunk = true;
                            }

                            assistantText = chunk.data.response;
                            if (assistantContentEl) {
                                assistantContentEl.innerHTML = this.formatMessage(assistantText);
                            }
                            this.scrollToBottom();
                        }
                    } else if (chunk.type === 'end') {
                        console.log('Stream end:', chunk.data);
                    } else if (chunk.type === 'error') {
                        console.error('Stream error:', chunk.data);
                    }
                },
                () => {
                    conversation.updatedAt = Date.now();
                    this.renderChatList();
                    this.isTyping = false;
                    this.handleInput();
                },
                (error) => {
                    this.hideTypingIndicator();
                    if (assistantContentEl) {
                        assistantContentEl.innerHTML = `<em>${this.escapeHtml(error.message || '发送消息时出错')}</em>`;
                    } else {
                        this.addErrorMessage(error.message || '发送消息时出错');
                    }
                    this.isTyping = false;
                    this.handleInput();
                },
                conversation.threadId
            );
        } catch (error) {
            this.hideTypingIndicator();
            this.addErrorMessage(error.message || '发送消息时出错');
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

        return messageDiv;
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

    async refreshConversationList() {
        const response = await api.conversationList();
        const list = Array.isArray(response?.data) ? response.data : [];

        const mapped = list
            .filter((item) => item && typeof item === 'object')
            .map((item) => this.mapConversationRecord(item))
            .filter((c) => c.threadId);

        mapped.sort((a, b) => {
            const at = this.parseTime(a.createdAt);
            const bt = this.parseTime(b.createdAt);
            if (bt !== at) return bt - at;
            return String(b.threadId).localeCompare(String(a.threadId));
        });

        const existingByThreadId = new Map(this.conversations.map((c) => [String(c.threadId), c]));
        this.conversations = mapped.map((c) => {
            const existing = existingByThreadId.get(String(c.threadId));
            return existing ? { ...c, title: existing.title || c.title, updatedAt: existing.updatedAt } : c;
        });
    }

    mapConversationRecord(record) {
        const threadId = record?.thread_id == null ? '' : String(record.thread_id);
        return {
            id: threadId,
            threadId,
            title: record?.name ? String(record.name) : threadId,
            createdAt: record?.create_time ? String(record.create_time) : '',
            updatedAt: Date.now()
        };
    }

    parseTime(value) {
        const ts = Date.parse(String(value || ''));
        return Number.isFinite(ts) ? ts : 0;
    }

    async createNewConversation(select) {
        const response = await api.conversationAdd();
        const record = response?.data;
        const conversation = this.mapConversationRecord(record);
        if (!conversation.threadId) {
            throw new Error('创建对话失败：未返回 thread_id');
        }

        this.conversations = [conversation, ...this.conversations.filter((c) => String(c.threadId) !== String(conversation.threadId))];

        if (select) {
            this.activeConversationId = conversation.id;
            this.renderChatList();
            this.renderMessages([]);
            this.closeSidebar();
        }

        return conversation;
    }

    getActiveConversation() {
        if (!this.activeConversationId) return null;
        return this.conversations.find((c) => c.id === this.activeConversationId) || null;
    }

    async loadAndRenderActiveConversation() {
        const conversation = this.getActiveConversation();
        if (!conversation) return;
        await this.loadAndRenderConversation(conversation.threadId);
    }

    async loadAndRenderConversation(threadId) {
        this.messagesContainer.innerHTML = '';
        this.showTypingIndicator();
        try {
            const response = await api.conversationSelect(threadId);
            const messages = Array.isArray(response?.data) ? response.data : [];
            this.renderMessages(messages);
        } finally {
            this.hideTypingIndicator();
        }
    }

    renderMessages(messages) {
        this.messagesContainer.innerHTML = '';

        if (!Array.isArray(messages) || messages.length === 0) {
            this.messagesContainer.innerHTML = this.welcomeTemplate || '';
            this.welcomeShown = true;
            return;
        }

        this.welcomeShown = false;
        for (const msg of messages) {
            const role = String(msg?.role || '').toLowerCase();
            const type = role === 'assistant' || role === 'ai' ? 'assistant' : 'user';
            this.addMessage(String(msg?.content || ''), type);
        }
        this.scrollToBottom();
    }

    renderChatList() {
        const activeId = this.activeConversationId;
        this.chatList.innerHTML = '';

        const conversations = this.conversations
            .slice()
            .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));

        for (const c of conversations) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `chat-item${c.id === activeId ? ' active' : ''}`;
            btn.dataset.conversationId = c.id;

            const title = document.createElement('div');
            title.className = 'chat-item-title';
            title.textContent = c.title || '新对话';
            btn.appendChild(title);

            btn.addEventListener('click', () => {
                this.activeConversationId = c.id;
                this.renderChatList();
                this.loadAndRenderConversation(c.threadId).catch((e) => this.addErrorMessage(e.message || '加载对话失败'));
                this.closeSidebar();
            });

            this.chatList.appendChild(btn);
        }
    }

    makeTitleFromMessage(message) {
        const cleaned = String(message).trim().replace(/\s+/g, ' ');
        if (!cleaned) return '新对话';
        return cleaned.length > 22 ? cleaned.slice(0, 22) + '…' : cleaned;
    }

    createId() {
        if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
            return crypto.randomUUID();
        }
        return `c_${Math.random().toString(16).slice(2)}_${Date.now().toString(16)}`;
    }

    openSidebar() {
        document.body.classList.add('sidebar-open');
    }

    closeSidebar() {
        document.body.classList.remove('sidebar-open');
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});
