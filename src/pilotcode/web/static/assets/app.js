// WebSocket connection
let ws = null;
let messageId = 0;
let pendingMessages = new Map();
let currentStreamId = null;
let isConnected = false;

// DOM elements
const chatArea = document.getElementById('chatArea');
const messagesContainer = document.getElementById('messagesContainer');
const welcomeMessage = document.getElementById('welcomeMessage');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const newSessionBtn = document.getElementById('newSessionBtn');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.querySelector('.sidebar');
const attachBtn = document.getElementById('attachBtn');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const inputStatus = document.getElementById('inputStatus');

// Initialize
function init() {
    connectWebSocket();
    setupEventListeners();
    // Initialize button state
    sendBtn.disabled = messageInput.value.trim().length === 0;
    messageInput.focus();
}

// WebSocket connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.hostname}:${parseInt(window.location.port) + 1}`;
    
    console.log('Connecting to WebSocket:', wsUrl);
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
        isConnected = true;
        updateConnectionStatus(true);
        showToast('Connected to PilotCode', 'success');
    };
    
    ws.onclose = () => {
        console.log('WebSocket closed');
        isConnected = false;
        updateConnectionStatus(false);
        setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleMessage(data);
        } catch (e) {
            console.error('Error parsing message:', e);
        }
    };
}

// Update connection status UI
function updateConnectionStatus(connected) {
    if (connected) {
        statusDot.classList.remove('disconnected');
        statusText.textContent = 'Connected';
    } else {
        statusDot.classList.add('disconnected');
        statusText.textContent = 'Disconnected';
    }
}

// Send message
function sendMessage(data) {
    console.log('Sending:', data.type, data);
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
    } else {
        showToast('Not connected to server', 'error');
        console.error('WebSocket not open, state:', ws ? ws.readyState : 'null');
    }
}

// Handle incoming messages
function handleMessage(data) {
    console.log('Received:', data.type);
    
    switch (data.type) {
        case 'streaming_start':
            handleStreamingStart(data);
            break;
        case 'streaming_chunk':
            handleStreamingChunk(data);
            break;
        case 'streaming_end':
            handleStreamingEnd(data);
            break;
        case 'streaming_error':
            handleStreamingError(data);
            break;
        case 'thinking':
            handleThinking(data);
            break;
        case 'tool_call':
            handleToolCall(data);
            break;
        case 'tool_result':
            handleToolResult(data);
            break;
        case 'permission_request':
            handlePermissionRequest(data);
            break;
        case 'permission_response':
            handlePermissionResponse(data);
            break;
        case 'permission_result':
            handlePermissionResult(data);
            break;
    }
}

// Handle streaming start
function handleStreamingStart(data) {
    currentStreamId = data.stream_id;
    hideWelcome();
    
    // Create stream container
    const streamDiv = document.createElement('div');
    streamDiv.id = `stream-${data.stream_id}`;
    streamDiv.className = 'message';
    streamDiv.innerHTML = `
        <div class="user-query">${escapeHtml(data.message)}</div>
        <div class="stream-content" id="content-${data.stream_id}"></div>
    `;
    messagesContainer.appendChild(streamDiv);
    pendingMessages.set(data.stream_id, { content: '' });
    scrollToBottom();
}

// Handle streaming chunk
function handleStreamingChunk(data) {
    const stream = pendingMessages.get(data.stream_id);
    if (!stream) return;
    
    // Append new content
    stream.content += data.chunk;
    
    const contentDiv = document.getElementById(`content-${data.stream_id}`);
    if (contentDiv) {
        // Check if we need to create final response container
        let finalDiv = contentDiv.querySelector('.final-response');
        if (!finalDiv) {
            finalDiv = document.createElement('div');
            finalDiv.className = 'final-response';
            contentDiv.appendChild(finalDiv);
        }
        // Use incremental rendering to avoid flicker and duplicates
        // Only render if content changed significantly
        if (data.chunk) {
            finalDiv.innerHTML = renderMarkdown(stream.content);
            scrollToBottom();
        }
    }
}

// Handle streaming end
function handleStreamingEnd(data) {
    pendingMessages.delete(data.stream_id);
    currentStreamId = null;
    setInputState(false);
}

// Handle streaming error
function handleStreamingError(data) {
    showToast(data.error || 'Streaming error', 'error');
    pendingMessages.delete(data.stream_id);
    currentStreamId = null;
    setInputState(false);
}

// Handle thinking block
function handleThinking(data) {
    const contentDiv = document.getElementById(`content-${currentStreamId}`);
    if (!contentDiv) return;
    
    // Check if thinking block already exists
    let thinkingDiv = contentDiv.querySelector('.stream-block.thinking');
    if (!thinkingDiv) {
        thinkingDiv = document.createElement('div');
        thinkingDiv.className = 'stream-block thinking';
        thinkingDiv.innerHTML = '<div class="label">Thinking</div><div class="thinking-content"></div>';
        // Insert before final response if exists
        const finalDiv = contentDiv.querySelector('.final-response');
        if (finalDiv) {
            contentDiv.insertBefore(thinkingDiv, finalDiv);
        } else {
            contentDiv.appendChild(thinkingDiv);
        }
    }
    
    const thinkingContent = thinkingDiv.querySelector('.thinking-content');
    thinkingContent.textContent = data.content;
    scrollToBottom();
}

// Handle tool call
function handleToolCall(data) {
    const contentDiv = document.getElementById(`content-${currentStreamId}`);
    if (!contentDiv) return;
    
    // Format input parameters in one line
    const inputStr = formatToolInput(data.tool_input);
    
    const toolDiv = document.createElement('div');
    toolDiv.className = 'tool-call';
    toolDiv.id = `tool-${data.tool_name}-${Date.now()}`;
    toolDiv.innerHTML = `
        <div class="tool-header" onclick="toggleTool(this)">
            <span class="icon">[T]</span>
            <span>${escapeHtml(data.tool_name)} ${inputStr}</span>
            <span style="margin-left: auto; color: #999;">▼</span>
        </div>
        <div class="tool-content hidden">
            <pre><code>${escapeHtml(JSON.stringify(data.tool_input, null, 2))}</code></pre>
        </div>
    `;
    
    // Insert before final response
    const finalDiv = contentDiv.querySelector('.final-response');
    if (finalDiv) {
        contentDiv.insertBefore(toolDiv, finalDiv);
    } else {
        contentDiv.appendChild(toolDiv);
    }
    scrollToBottom();
}

// Format tool input to single line (no brackets)
function formatToolInput(input) {
    if (!input || typeof input !== 'object') return '';
    const pairs = Object.entries(input).map(([k, v]) => {
        let val = v;
        if (typeof v === 'string') {
            if (v.length > 40) {
                val = v.substring(0, 20) + '...';
            } else {
                val = v;
            }
        } else if (Array.isArray(v)) {
            val = v.join(', ');
            if (val.length > 30) val = val.substring(0, 25) + '...';
        }
        return `${k}=${val}`;
    });
    return pairs.join(' ');
}

// Handle tool result
function handleToolResult(data) {
    const contentDiv = document.getElementById(`content-${currentStreamId}`);
    if (!contentDiv) return;
    
    // Truncate long results - shorter max for cleaner UI
    let resultText = data.result || '';
    const maxLen = 120;
    if (resultText.length > maxLen) {
        resultText = resultText.substring(0, 50) + ' ... ' + resultText.substring(resultText.length - 30);
    }
    
    const resultDiv = document.createElement('div');
    resultDiv.className = 'stream-block result';
    resultDiv.innerHTML = `<pre><code>${escapeHtml(resultText)}</code></pre>`;
    
    // Insert before final response
    const finalDiv = contentDiv.querySelector('.final-response');
    if (finalDiv) {
        contentDiv.insertBefore(resultDiv, finalDiv);
    } else {
        contentDiv.appendChild(resultDiv);
    }
    scrollToBottom();
}

// Handle permission request
function handlePermissionRequest(data) {
    const contentDiv = document.getElementById(`content-${currentStreamId}`);
    if (!contentDiv) return;
    
    // Check if permission block already exists for this request
    const existingPerm = document.getElementById(`perm-${data.request_id}`);
    if (existingPerm) return;
    
    const riskClass = `risk-${data.risk_level}`;
    const riskText = data.risk_level.charAt(0).toUpperCase() + data.risk_level.slice(1);
    
    // Format input compactly
    const inputStr = formatToolInput(data.tool_input);
    
    const permDiv = document.createElement('div');
    permDiv.id = `perm-${data.request_id}`;
    permDiv.className = 'permission-request';
    permDiv.innerHTML = `
        <div class="permission-header">
            <span class="perm-icon">[P]</span>
            <span class="perm-tool">${escapeHtml(data.tool_name)}</span>
            <span class="risk-badge ${riskClass}">${riskText}</span>
        </div>
        <div class="permission-input-compact">${escapeHtml(inputStr)}</div>
        <div class="permission-actions">
            <button class="perm-btn deny" onclick="respondPermission('${data.request_id}', false, false)">Deny</button>
            <button class="perm-btn allow-once" onclick="respondPermission('${data.request_id}', true, false)">Allow Once</button>
            <button class="perm-btn allow-session" onclick="respondPermission('${data.request_id}', true, true)">Allow for Session</button>
        </div>
    `;
    
    // Insert before final response
    const finalDiv = contentDiv.querySelector('.final-response');
    if (finalDiv) {
        contentDiv.insertBefore(permDiv, finalDiv);
    } else {
        contentDiv.appendChild(permDiv);
    }
    scrollToBottom();
}

// Handle permission response (from server)
function handlePermissionResponse(data) {
    // Server acknowledging our response
}

// Handle permission result
function handlePermissionResult(data) {
    const permDiv = document.getElementById(`perm-${data.request_id}`);
    if (!permDiv) return;
    
    const actions = permDiv.querySelector('.permission-actions');
    if (actions) {
        if (data.granted) {
            const levelText = data.level === 'session' ? 'allowed for session' : 'allowed';
            actions.innerHTML = `<span style="color: #166534; font-weight: 500;">✓ ${levelText}</span>`;
        } else {
            actions.innerHTML = `<span style="color: #991b1b; font-weight: 500;">✗ Denied</span>`;
        }
    }
}

// Respond to permission request
function respondPermission(requestId, granted, forSession = false) {
    console.log('Responding to permission:', requestId, granted, forSession);
    sendMessage({
        type: 'permission_response',
        request_id: requestId,
        granted: granted,
        for_session: forSession
    });
    // Update UI immediately to show response sent
    const permDiv = document.getElementById(`perm-${requestId}`);
    if (permDiv) {
        const actions = permDiv.querySelector('.permission-actions');
        if (actions) {
            actions.innerHTML = '<span style="color: #666;">Processing...</span>';
        }
    }
}

// Toggle tool content visibility
function toggleTool(header) {
    const content = header.nextElementSibling;
    const arrow = header.querySelector('span:last-child');
    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        arrow.textContent = '▼';
    } else {
        content.classList.add('hidden');
        arrow.textContent = '▶';
    }
}

// Setup event listeners
function setupEventListeners() {
    // Send on Enter (without Shift)
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendUserMessage();
        }
    });
    
    // Auto-resize textarea
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';
        sendBtn.disabled = messageInput.value.trim().length === 0;
    });
    
    // Send button
    sendBtn.addEventListener('click', sendUserMessage);
    
    // New session
    newSessionBtn.addEventListener('click', () => {
        messagesContainer.innerHTML = '';
        messagesContainer.classList.add('hidden');
        welcomeMessage.classList.remove('hidden');
        messageInput.value = '';
        messageInput.style.height = 'auto';
        sendBtn.disabled = true;
        messageId = 0;
        pendingMessages.clear();
        currentStreamId = null;
    });
    
    // Sidebar toggle
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('hidden');
    });
    
    // Attach button (placeholder - file upload not implemented yet)
    attachBtn.addEventListener('click', () => {
        showToast('File upload coming soon', 'info');
    });
}

// Send user message
function sendUserMessage() {
    const content = messageInput.value.trim();
    if (!content || !isConnected) return;
    
    setInputState(true);
    
    const msgId = ++messageId;
    
    sendMessage({
        type: 'query',
        message: content,
        message_id: msgId
    });
    
    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendBtn.disabled = true;
}

// Set input state
function setInputState(loading) {
    if (loading) {
        inputStatus.textContent = 'Processing...';
        messageInput.disabled = true;
        sendBtn.disabled = true;
    } else {
        inputStatus.textContent = 'Ready';
        messageInput.disabled = false;
        messageInput.focus();
    }
}

// Hide welcome message
function hideWelcome() {
    welcomeMessage.classList.add('hidden');
    messagesContainer.classList.remove('hidden');
}

// Scroll to bottom
function scrollToBottom() {
    chatArea.scrollTop = chatArea.scrollHeight;
}

// Render markdown (simple version)
function renderMarkdown(text) {
    if (!text) return '';
    
    // Escape HTML
    text = escapeHtml(text);
    
    // Code blocks - process first to preserve newlines
    const codeBlocks = [];
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const id = codeBlocks.length;
        // Store code with original newlines preserved
        codeBlocks.push({ lang: lang || 'text', code: code.trim() });
        return `__CODE_BLOCK_${id}__`;
    });
    
    // Inline code
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Bold
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    
    // Italic
    text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    
    // Links
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    
    // Lists
    text = text.replace(/^(\s*)-\s+(.+)$/gm, (match, indent, item) => {
        return `<li style="margin-left: ${indent.length * 8}px">${item}</li>`;
    });
    
    // Line breaks (outside code blocks)
    text = text.replace(/\n/g, '<br>');
    
    // Restore code blocks
    codeBlocks.forEach((block, id) => {
        // Escape HTML in code, but preserve newlines as actual newlines for <pre>
        const escapedCode = block.code.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        text = text.replace(`__CODE_BLOCK_${id}__`, `<div class="code-block">
            <div class="code-header">
                <span>${block.lang}</span>
                <button class="copy-btn" onclick="copyCode(this)">Copy</button>
            </div>
            <pre><code>${escapedCode}</code></pre>
        </div>`);
    });
    
    return text;
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Copy code to clipboard
function copyCode(btn) {
    const codeBlock = btn.closest('.code-block').querySelector('code');
    // Get the HTML content and decode HTML entities to preserve newlines
    let code = codeBlock.innerHTML;
    // Convert <br> to newlines
    code = code.replace(/<br\s*\/?>/gi, '\n');
    // Create a temp element to decode HTML entities
    const temp = document.createElement('textarea');
    temp.innerHTML = code;
    code = temp.value;
    navigator.clipboard.writeText(code).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy', 2000);
    });
}

// Show toast notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Initialize on load
init();
