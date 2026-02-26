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
        this.currentStatusPanel = null;
        this.currentStatusList = [];

        this.init();
    }

    init() {
        this.messageInput.addEventListener('input', () => this.handleInput());
        this.messageInput.addEventListener('keydown', (e) => this.handleKeyDown(e));
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('input', () => this.autoResizeInput());

        this.newChatButton.addEventListener('click', () => {
            this.activeConversationId = null;
            this.renderChatList();
            this.renderMessages([]);
            this.closeSidebar();
        });
        this.sidebarToggle.addEventListener('click', () => this.openSidebar());
        this.sidebarClose.addEventListener('click', () => this.closeSidebar());
        this.sidebarBackdrop.addEventListener('click', () => this.closeSidebar());

        this.welcomeTemplate = this.messagesContainer.querySelector('.welcome-message')?.outerHTML || '';
        this.bootstrap().catch((e) => this.addErrorMessage(e.message || '加载对话失败'));
    }

    async bootstrap() {
        await this.refreshConversationList();
        this.renderChatList();
        this.renderMessages([]);
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
            conversation = await this.createNewConversation(false, message);
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

        // 创建状态面板
        this.createStatusPanel();

        this.showTypingIndicator();

        try {
            let assistantMessageDiv = null;
            let assistantContentEl = null;
            let assistantText = '';
            let receivedFirstChunk = false;

            await api.chatStream(
                message,
                (chunk) => {
                    if (chunk.type === 'token') {
                        // 只有收到 token 数据时才创建消息气泡
                        if (!receivedFirstChunk) {
                            this.hideTypingIndicator();
                            receivedFirstChunk = true;
                            assistantMessageDiv = this.addMessage('', 'assistant');
                            assistantContentEl = assistantMessageDiv.querySelector('.message-content');
                        }

                        const token = chunk.data?.content || '';
                        assistantText += token;
                        if (assistantContentEl) {
                            assistantContentEl.innerHTML = this.formatMessage(assistantText);
                        }
                        this.scrollToBottom();
                    } else if (chunk.type === 'status') {
                        // AI 状态更新
                        this.updateStatusPanel(chunk.data?.status || '');
                    } else if (chunk.type === 'chunk') {
                        // 兼容旧版 chunk 事件
                        if (chunk.data.response) {
                            if (!receivedFirstChunk) {
                                this.hideTypingIndicator();
                                receivedFirstChunk = true;
                                assistantMessageDiv = this.addMessage('', 'assistant');
                                assistantContentEl = assistantMessageDiv.querySelector('.message-content');
                            }

                            assistantText = chunk.data.response;
                            if (assistantContentEl) {
                                assistantContentEl.innerHTML = this.formatMessage(assistantText);
                            }
                            this.scrollToBottom();
                        }
                    } else if (chunk.type === 'workflow_end') {
                        console.log('Workflow end');
                        this.finishStatusPanel();
                    } else if (chunk.type === 'end') {
                        console.log('Stream end:', chunk.data);
                    } else if (chunk.type === 'error') {
                        console.error('Stream error:', chunk.data);
                    } else if (chunk.type === 'heartbeat') {
                        // 心跳，保持连接
                    } else if (chunk.type === 'waiting_for_approval') {
                        // 人机交互中断，显示规划审批卡片
                        this.hideTypingIndicator();
                        this.showApprovalPanel(chunk.data);
                    }
                },
                () => {
                    // 如果没有收到任何 token，移除空的消息气泡
                    if (!receivedFirstChunk && assistantMessageDiv) {
                        assistantMessageDiv.remove();
                    }
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
                    this.currentStatusPanel = null;
                    this.currentStatusList = [];
                },
                conversation.threadId
            );
        } catch (error) {
            this.hideTypingIndicator();
            this.addErrorMessage(error.message || '发送消息时出错');
            this.isTyping = false;
            this.handleInput();
            this.currentStatusPanel = null;
            this.currentStatusList = [];
        }
    }

    /**
     * 添加消息到界面
     */
    addMessage(content, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = this.formatMessage(content);

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

    async createNewConversation(select, question) {
        const response = await api.conversationAdd(question);
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

    async deleteConversation(conversation) {
        if (!conversation || !conversation.threadId) return;
        const title = conversation.title || conversation.threadId;
        const shouldDelete = typeof window !== 'undefined' && typeof window.confirm === 'function'
            ? window.confirm(`确定删除对话「${title}」吗？`)
            : true;
        if (!shouldDelete) return;

        if (this.isTyping && this.activeConversationId === conversation.id) {
            throw new Error('正在生成回复，无法删除当前对话');
        }

        await api.conversationDelete(conversation.threadId);

        this.conversations = this.conversations.filter((c) => c.id !== conversation.id);
        if (this.activeConversationId === conversation.id) {
            this.activeConversationId = null;
            this.renderMessages([]);
        }
        this.renderChatList();
        await this.refreshConversationList();
        this.renderChatList();
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

            const del = document.createElement('span');
            del.className = 'chat-item-delete';
            del.setAttribute('role', 'button');
            del.setAttribute('tabindex', '0');
            del.setAttribute('aria-label', '删除对话');
            del.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M3 6h18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                    <path d="M8 6V4h8v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                    <path d="M19 6l-1 14H6L5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                    <path d="M10 11v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                    <path d="M14 11v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                </svg>
            `.trim();
            del.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.deleteConversation(c).catch((err) => this.addErrorMessage(err?.message || '删除对话失败'));
            });
            del.addEventListener('keydown', (e) => {
                if (e.key !== 'Enter' && e.key !== ' ') return;
                e.preventDefault();
                e.stopPropagation();
                this.deleteConversation(c).catch((err) => this.addErrorMessage(err?.message || '删除对话失败'));
            });
            btn.appendChild(del);

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

    /**
     * 创建状态面板
     */
    createStatusPanel(insertAfterElement = null) {
        this.currentStatusList = [];

        const statusDiv = document.createElement('div');
        statusDiv.className = 'agent-status';

        const header = document.createElement('div');
        header.className = 'status-header';
        header.innerHTML = `
            <div class="status-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 6v6l4 2"/>
                </svg>
            </div>
            <span class="status-title">思考中</span>
            <div class="status-toggle">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M6 9l6 6 6-6"/>
                </svg>
            </div>
        `;

        const content = document.createElement('div');
        content.className = 'status-content';
        content.innerHTML = '<ul class="status-list"></ul>';

        // 点击展开/折叠
        header.addEventListener('click', () => {
            header.classList.toggle('expanded');
        });

        statusDiv.appendChild(header);
        statusDiv.appendChild(content);

        // 如果指定了插入位置，则插入到该元素之后
        if (insertAfterElement) {
            insertAfterElement.after(statusDiv);
        } else {
            // 插入到用户消息之后
            const messages = this.messagesContainer.querySelectorAll('.message');
            const lastUserMessage = Array.from(messages).filter(m => m.classList.contains('user')).pop();
            if (lastUserMessage) {
                lastUserMessage.after(statusDiv);
            } else {
                this.messagesContainer.appendChild(statusDiv);
            }
        }

        this.currentStatusPanel = { header, content, list: content.querySelector('.status-list') };
        this.scrollToBottom();
    }

    /**
     * 更新状态面板
     */
    updateStatusPanel(statusText) {
        if (!this.currentStatusPanel) return;

        // 添加新状态
        this.currentStatusList.push({ status: statusText });

        const li = document.createElement('li');
        li.className = 'status-item active';
        li.innerHTML = `
            <span class="status-item-dot"></span>
            <span class="status-item-text">${statusText}</span>
        `;
        this.currentStatusPanel.list.appendChild(li);

        this.scrollToBottom();
    }

    /**
     * 结束状态面板
     */
    finishStatusPanel() {
        if (!this.currentStatusPanel) return;

        // 标记最后一个状态为完成
        const items = this.currentStatusPanel.list.querySelectorAll('.status-item');
        if (items.length > 0) {
            const lastItem = items[items.length - 1];
            lastItem.classList.remove('active');
            lastItem.classList.add('completed');
        }

        // 更新图标为完成状态
        const icon = this.currentStatusPanel.header.querySelector('.status-icon');
        icon.classList.remove('idle');
        icon.classList.add('completed');
        icon.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M9 12l2 2 4-4"/>
            </svg>
        `;

        this.currentStatusPanel = null;
        this.currentStatusList = [];
    }

    /**
     * 显示规划审批卡片
     */
    showApprovalPanel(data) {
        const plan = data?.plan || [];
        const conversation = this.getActiveConversation();
        const threadId = conversation?.threadId;

        // 保存原始计划，供批准时使用
        const originalPlan = [...plan];

        // 创建审批面板
        const approvalDiv = document.createElement('div');
        approvalDiv.className = 'approval-panel';
        approvalDiv.dataset.originalPlan = JSON.stringify(originalPlan);

        let planHtml = '';
        plan.forEach((item, index) => {
            planHtml += `
                <div class="approval-plan-item" data-index="${index}">
                    <span class="plan-number">${index + 1}</span>
                    <textarea class="plan-input" data-index="${index}">${this.escapeHtml(item)}</textarea>
                    <button class="btn-delete-item" title="删除此步骤">✕</button>
                </div>
            `;
        });

        approvalDiv.innerHTML = `
            <div class="approval-header">
                <span class="approval-title">请确认旅行规划</span>
            </div>
            <div class="approval-plan-list">
                ${planHtml}
            </div>
            <div class="approval-add-section">
                <button class="btn-add-item">+ 添加步骤</button>
            </div>
            <div class="approval-actions">
                <button class="btn-approve">批准执行</button>
                <button class="btn-modify">修改计划</button>
                <button class="btn-cancel">取消任务</button>
            </div>
        `;

        this.messagesContainer.appendChild(approvalDiv);
        this.scrollToBottom();

        // 根据内容自动调整 textarea 高度
        const textareas = approvalDiv.querySelectorAll('.plan-input');
        textareas.forEach(textarea => {
            textarea.style.height = 'auto';
            textarea.style.height = textarea.scrollHeight + 'px';
        });

        // 绑定事件
        const btnApprove = approvalDiv.querySelector('.btn-approve');
        const btnModify = approvalDiv.querySelector('.btn-modify');
        const btnCancel = approvalDiv.querySelector('.btn-cancel');
        const btnAddItem = approvalDiv.querySelector('.btn-add-item');

        // 删除单个步骤
        approvalDiv.querySelectorAll('.btn-delete-item').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const item = e.target.closest('.approval-plan-item');
                item.remove();
                this.updatePlanNumbers(approvalDiv);
            });
        });

        // 添加新步骤
        btnAddItem.addEventListener('click', () => {
            const planList = approvalDiv.querySelector('.approval-plan-list');
            const newIndex = planList.children.length;
            const newItem = document.createElement('div');
            newItem.className = 'approval-plan-item';
            newItem.dataset.index = newIndex;
            newItem.innerHTML = `
                <span class="plan-number">${newIndex + 1}</span>
                <textarea class="plan-input" data-index="${newIndex}" placeholder="输入新步骤..."></textarea>
                <button class="btn-delete-item" title="删除此步骤">✕</button>
            `;
            planList.appendChild(newItem);
            newItem.querySelector('textarea').focus();
            // 绑定删除事件
            newItem.querySelector('.btn-delete-item').addEventListener('click', (e) => {
                const item = e.target.closest('.approval-plan-item');
                item.remove();
                this.updatePlanNumbers(approvalDiv);
            });
        });

        // 更新步骤序号
        this.updatePlanNumbers = function(panel) {
            const items = panel.querySelectorAll('.approval-plan-item');
            items.forEach((item, idx) => {
                item.querySelector('.plan-number').textContent = idx + 1;
                item.querySelector('.plan-input').dataset.index = idx;
            });
        };

        // 批准（使用当前UI中的计划，反映用户的删除/修改）
        btnApprove.addEventListener('click', () => {
            const inputs = approvalDiv.querySelectorAll('.plan-input');
            const currentPlan = Array.from(inputs).map(input => input.value.trim()).filter(p => p);
            this.submitApproval(threadId, true, currentPlan, false, approvalDiv);
        });

        // 修改
        btnModify.addEventListener('click', () => {
            const inputs = approvalDiv.querySelectorAll('.plan-input');
            const modifiedPlan = Array.from(inputs).map(input => input.value.trim()).filter(p => p);
            this.submitApproval(threadId, true, modifiedPlan, false, approvalDiv);
        });

        // 取消
        btnCancel.addEventListener('click', () => {
            this.submitApproval(threadId, false, [], true, approvalDiv);
        });
    }

    /**
     * 提交审批
     */
    async submitApproval(threadId, approved, plan, cancelled, panel) {
        if (!threadId) return;

        // 禁用按钮
        const buttons = panel.querySelectorAll('button');
        buttons.forEach(btn => btn.disabled = true);

        this.isTyping = true;

        // 不移除审批面板，而是更新状态
        const statusMsg = cancelled ? '用户取消了任务' : '用户已确认规划';

        // 找到按钮区域并替换为状态显示
        const buttonArea = panel.querySelector('.approval-actions');
        if (buttonArea) {
            buttonArea.innerHTML = `<div class="approval-status">✓ ${statusMsg}</div>`;
        }

        // 显示打字 indicator
        this.showTypingIndicator();

        // 重新创建状态面板，以便接收后端的 status 消息
        // 传入审批卡片作为插入位置参考，使其显示在卡片下方
        this.createStatusPanel(panel);

        let assistantMessageDiv = null;
        let assistantContentEl = null;
        let assistantText = '';
        let receivedFirstChunk = false;

        try {
            await api.approveStream(
                threadId,
                approved,
                plan,
                cancelled,
                (chunk) => {
                    if (chunk.type === 'token') {
                        // 只有收到 token 数据时才创建消息气泡
                        if (!receivedFirstChunk) {
                            this.hideTypingIndicator();
                            receivedFirstChunk = true;
                            assistantMessageDiv = this.addMessage('', 'assistant');
                            assistantContentEl = assistantMessageDiv.querySelector('.message-content');
                        }
                        const token = chunk.data?.content || '';
                        assistantText += token;
                        if (assistantContentEl) {
                            assistantContentEl.innerHTML = this.formatMessage(assistantText);
                        }
                        this.scrollToBottom();
                    } else if (chunk.type === 'status') {
                        this.updateStatusPanel(chunk.data?.status || '');
                    } else if (chunk.type === 'workflow_end') {
                        this.finishStatusPanel();
                    } else if (chunk.type === 'error') {
                        console.error('Stream error:', chunk.data);
                    }
                },
                () => {
                    this.hideTypingIndicator();
                    // 如果没有收到任何 token，移除空的消息气泡
                    if (!receivedFirstChunk && assistantMessageDiv) {
                        assistantMessageDiv.remove();
                    }
                    this.isTyping = false;
                    this.handleInput();
                },
                (error) => {
                    this.hideTypingIndicator();
                    if (assistantContentEl) {
                        assistantContentEl.innerHTML = `<em>${this.escapeHtml(error.message || '审批提交失败')}</em>`;
                    }
                    this.isTyping = false;
                    this.handleInput();
                }
            );
        } catch (error) {
            this.hideTypingIndicator();
            this.addErrorMessage(error.message || '审批提交失败');
            this.isTyping = false;
            this.handleInput();
        }
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});
