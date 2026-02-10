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
        this.storageKey = 'travelassistant_conversations_v1';
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

        this.newChatButton.addEventListener('click', () => this.createNewConversation(true));
        this.sidebarToggle.addEventListener('click', () => this.openSidebar());
        this.sidebarClose.addEventListener('click', () => this.closeSidebar());
        this.sidebarBackdrop.addEventListener('click', () => this.closeSidebar());

        this.welcomeTemplate = this.messagesContainer.querySelector('.welcome-message')?.outerHTML || '';

        this.loadConversations();
        if (this.conversations.length === 0) {
            const conversation = this.createNewConversation(false);
            this.activeConversationId = conversation.id;
        } else {
            this.activeConversationId = this.conversations[0].id;
        }

        this.renderChatList();
        this.renderActiveConversation();
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

        const conversation = this.getActiveConversation() || this.createNewConversation(false);
        this.activeConversationId = conversation.id;
        this.renderChatList();

        if (this.welcomeShown) {
            const welcomeMessage = this.messagesContainer.querySelector('.welcome-message');
            if (welcomeMessage) welcomeMessage.remove();
            this.welcomeShown = false;
        }

        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        this.sendButton.disabled = true;

        const now = Date.now();
        conversation.updatedAt = now;
        if (!conversation.title || conversation.title === '新对话') {
            conversation.title = this.makeTitleFromMessage(message);
        }
        conversation.messages.push({ role: 'user', content: message, ts: now });
        this.saveConversations();

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
                    if (assistantText) {
                        const doneAt = Date.now();
                        conversation.updatedAt = doneAt;
                        conversation.messages.push({ role: 'assistant', content: assistantText, ts: doneAt });
                        this.saveConversations();
                        this.renderChatList();
                    }
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

    loadConversations() {
        try {
            const raw = localStorage.getItem(this.storageKey);
            const parsed = raw ? JSON.parse(raw) : [];
            if (!Array.isArray(parsed)) return;

            this.conversations = parsed
                .filter((c) => c && typeof c === 'object')
                .map((c) => ({
                    id: String(c.id || this.createId()),
                    threadId: String(c.threadId || c.id || this.createId()),
                    title: typeof c.title === 'string' ? c.title : '新对话',
                    createdAt: typeof c.createdAt === 'number' ? c.createdAt : Date.now(),
                    updatedAt: typeof c.updatedAt === 'number' ? c.updatedAt : Date.now(),
                    messages: Array.isArray(c.messages)
                        ? c.messages
                              .filter((m) => m && typeof m === 'object')
                              .map((m) => ({
                                  role: m.role === 'assistant' ? 'assistant' : 'user',
                                  content: typeof m.content === 'string' ? m.content : '',
                                  ts: typeof m.ts === 'number' ? m.ts : Date.now()
                              }))
                        : []
                }))
                .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
        } catch {
            this.conversations = [];
        }
    }

    saveConversations() {
        const compact = this.conversations
            .slice()
            .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
            .slice(0, 60);
        this.conversations = compact;
        localStorage.setItem(this.storageKey, JSON.stringify(compact));
    }

    createNewConversation(select) {
        const now = Date.now();
        const id = this.createId();
        const conversation = {
            id,
            threadId: id,
            title: '新对话',
            createdAt: now,
            updatedAt: now,
            messages: []
        };

        this.conversations.unshift(conversation);
        this.saveConversations();

        if (select) {
            this.activeConversationId = conversation.id;
            this.renderChatList();
            this.renderActiveConversation();
            this.closeSidebar();
        }

        return conversation;
    }

    getActiveConversation() {
        if (!this.activeConversationId) return null;
        return this.conversations.find((c) => c.id === this.activeConversationId) || null;
    }

    renderActiveConversation() {
        const conversation = this.getActiveConversation();
        if (!conversation) {
            this.messagesContainer.innerHTML = this.welcomeTemplate || '';
            this.welcomeShown = true;
            return;
        }
        this.renderConversation(conversation);
    }

    renderConversation(conversation) {
        this.messagesContainer.innerHTML = '';

        if (!conversation.messages || conversation.messages.length === 0) {
            this.messagesContainer.innerHTML = this.welcomeTemplate || '';
            this.welcomeShown = true;
            return;
        }

        this.welcomeShown = false;
        for (const msg of conversation.messages) {
            this.addMessage(msg.content, msg.role === 'assistant' ? 'assistant' : 'user');
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
                this.renderConversation(c);
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
