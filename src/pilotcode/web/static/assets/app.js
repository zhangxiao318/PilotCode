// WebSocket connection
let ws = null;
let messageId = 0;
let pendingMessages = new Map();
let currentStreamId = null;
let isConnected = false;
let _wsConnecting = false;  // Guard against duplicate connect attempts
let currentSessionId = null;
let sessions = [];
let expandedGroups = new Set();
let archivedExpanded = false;
let contextMenuSessionId = null;
let isSending = false;

// Explorer state
let fileTreeData = null;
let gitStatusData = null;
let expandedDirs = new Set();
let selectedFile = null;
let activeExplorerTab = 'files';
let selectedDiffFile = null;
let gitCommitLog = [];
let gitCommitIndex = -1; // -1 = working tree, 0 = HEAD, 1 = HEAD~1, ...
let gitBranches = {current: '', local: [], remote: []};

// Refresh debouncing
let _lastRefreshTime = 0;
const _REFRESH_DEBOUNCE_MS = 2000;
// Lazy-loaded directory children cache: path -> children[]
let _lazyDirCache = {};

// DOM elements
const chatArea = document.getElementById('chatArea');
const messagesContainer = document.getElementById('messagesContainer');
const welcomeMessage = document.getElementById('welcomeMessage');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const stopBtn = document.getElementById('stopBtn');
const newSessionBtn = document.getElementById('newSessionBtn');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.querySelector('.sidebar');
const attachBtn = document.getElementById('attachBtn');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const inputStatus = document.getElementById('inputStatus');

// Toolbar DOM elements
const toolbarPathText = document.getElementById('toolbarPathText');
const toolbarPath = document.getElementById('toolbarPath');
const toolbarExplorerBtn = document.getElementById('toolbarExplorerBtn');

// Explorer DOM elements
const explorerPanel = document.getElementById('explorerPanel');
const explorerResizer = document.getElementById('explorerResizer');
const explorerToggle = document.getElementById('explorerToggle');
const explorerBody = document.getElementById('explorerBody');
const explorerCwd = document.getElementById('explorerCwd');
const fileTree = document.getElementById('fileTree');
const gitBar = document.getElementById('gitBar');
const gitFileList = document.getElementById('gitFileList');
const explorerTabs = document.getElementById('explorerTabs');
const tabFiles = document.getElementById('tabFiles');
const tabChanges = document.getElementById('tabChanges');
const filesTabContent = document.getElementById('filesTabContent');
const changesTabContent = document.getElementById('changesTabContent');
const changesBadge = document.getElementById('changesBadge');
const diffViewer = document.getElementById('diffViewer');
const diffFileName = document.getElementById('diffFileName');
const diffClose = document.getElementById('diffClose');
const diffContent = document.getElementById('diffContent');

// Git history DOM elements
const gitHistoryNav = document.getElementById('gitHistoryNav');
const gitPrevBtn = document.getElementById('gitPrevBtn');
const gitNextBtn = document.getElementById('gitNextBtn');
const gitLatestBtn = document.getElementById('gitLatestBtn');
const gitHistoryLabel = document.getElementById('gitHistoryLabel');
const gitBranchSelect = document.getElementById('gitBranchSelect');
const gitAheadBehind = document.getElementById('gitAheadBehind');
const commitInfo = document.getElementById('commitInfo');
const commitHash = document.getElementById('commitHash');
const commitMessage = document.getElementById('commitMessage');
const commitMeta = document.getElementById('commitMeta');

// Context usage DOM elements
const contextUsage = document.getElementById('contextUsage');
const contextPercent = document.getElementById('contextPercent');
const contextFill = document.getElementById('contextFill');
const tooltipTokens = document.getElementById('tooltipTokens');
const tooltipUsable = document.getElementById('tooltipUsable');
const tooltipWindow = document.getElementById('tooltipWindow');
const tooltipOutput = document.getElementById('tooltipOutput');

// Modal elements
const cwdModal = document.getElementById('cwdModal');
const cwdSearch = document.getElementById('cwdSearch');
const cwdCurrentPath = document.getElementById('cwdCurrentPath');
const cwdCurrentItem = document.getElementById('cwdCurrentItem');
const cwdRecentList = document.getElementById('cwdRecentList');
const cwdModalConfirm = document.getElementById('cwdModalConfirm');
const cwdModalCancel = document.getElementById('cwdModalCancel');
const cwdModalClose = document.getElementById('cwdModalClose');
let selectedCwd = null;
let cwdOptionsData = {current: '/', recent: []};

// Initialize
function init() {
    connectWebSocket();
    setupEventListeners();
    // Initialize button state
    sendBtn.disabled = messageInput.value.trim().length === 0;
    updateToolbarActiveStates();
    // Restore explorer width
    try {
        const savedWidth = localStorage.getItem('explorerWidth');
        if (savedWidth && explorerPanel) {
            explorerPanel.style.width = savedWidth;
            explorerPanel.style.minWidth = savedWidth;
        }
    } catch (e) {
        // ignore
    }
    messageInput.focus();
}

// WebSocket connection
function connectWebSocket() {
    if (_wsConnecting || (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN))) {
        return;
    }
    _wsConnecting = true;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.hostname}:${parseInt(window.location.port) + 1}`;
    
    console.log('Connecting to WebSocket:', wsUrl);
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        _wsConnecting = false;
        console.log('WebSocket connected');
        isConnected = true;
        updateConnectionStatus(true);
        showToast('Connected to PilotCode', 'success');
        // Request session list on connect
        sendMessage({type: 'session_list'});
    };
    
    ws.onclose = () => {
        _wsConnecting = false;
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
        case 'streaming_complete':
            pendingMessages.delete(data.stream_id);
            currentStreamId = null;
            setInputState(false);
            break;
        case 'streaming_error':
            handleStreamingError(data);
            break;
        case 'interrupted':
            showToast(data.message || 'Query interrupted', 'info');
            pendingMessages.delete(currentStreamId);
            currentStreamId = null;
            setInputState(false);
            break;
        case 'thinking':
            handleThinking(data);
            break;
        case 'reasoning':
            handleReasoning(data);
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
        case 'user_question_request':
            handleUserQuestionRequest(data);
            break;
        case 'cwd_options':
            cwdOptionsData = {
                current: data.current || '/',
                recent: data.recent || [],
            };
            renderCwdModal();
            showCwdModal();
            break;
        case 'session_created':
            currentSessionId = data.session_id;
            localStorage.setItem('pilotcode_last_session', data.session_id);
            if (data.cwd) {
                expandedGroups.add(data.cwd);
            }
            renderSessionList();
            refreshExplorer();
            updateToolbarPath(data.cwd || '');
            if (data.context) renderContextUsage(data.context);
            showToast(`New session created (${data.cwd || ''})`, 'success');
            break;
        case 'session_attached':
            currentSessionId = data.session_id;
            localStorage.setItem('pilotcode_last_session', data.session_id);
            renderSessionList();
            showToast(`Attached to session ${data.session_id.slice(0, 8)}`, 'success');
            refreshExplorer();
            updateToolbarPath(data.cwd || '');
            if (data.context) renderContextUsage(data.context);
            break;
        case 'session_loaded':
            currentSessionId = data.session_id;
            localStorage.setItem('pilotcode_last_session', data.session_id);
            clearChatUI();
            updateToolbarPath(data.project_path || data.cwd || '');
            if (data.context) renderContextUsage(data.context);
            if (data.messages && data.messages.length > 0) {
                renderHistoryMessages(data.messages);
            }
            renderSessionList();
            showToast(`Loaded: ${data.name || data.session_id}`, 'success');
            refreshExplorer();
            break;
        case 'session_list':
            sessions = data.sessions || [];
            renderSessionList();
            // Auto-restore last session on page refresh, or create a new one
            const lastSession = localStorage.getItem('pilotcode_last_session');
            if (lastSession && sessions.some(s => s.session_id === lastSession)) {
                sendMessage({type: 'session_load', session_id: lastSession});
            } else if (!currentSessionId) {
                // No previous session — auto-create one with server's default cwd
                sendMessage({type: 'session_create'});
            }
            break;
        case 'session_saved':
            showToast('Session saved', 'success');
            break;
        case 'session_deleted':
            sessions = sessions.filter(s => s.session_id !== data.session_id);
            renderSessionList();
            if (currentSessionId === data.session_id) {
                currentSessionId = null;
                localStorage.removeItem('pilotcode_last_session');
                clearChatUI();
                updateToolbarPath('');
                if (contextUsage) contextUsage.classList.add('hidden');
            }
            break;
        case 'session_renamed':
            sessions = sessions.map(s => s.session_id === data.session_id ? {...s, name: data.name} : s);
            renderSessionList();
            showToast('Session renamed', 'success');
            break;
        case 'session_archived':
            sessions = sessions.map(s => s.session_id === data.session_id ? {...s, archived: data.archived} : s);
            renderSessionList();
            showToast(data.archived ? 'Session archived' : 'Session unarchived', 'success');
            break;
        case 'server_info':
            const versionEl = document.getElementById('brandVersion');
            if (versionEl && data.version) versionEl.textContent = 'v' + data.version;
            break;
        case 'system':
            // System notifications (e.g. slash-command results, loop-guard msgs)
            if (data.stream_id && data.content) {
                const contentDiv = document.getElementById(`content-${data.stream_id}`);
                if (contentDiv) {
                    let sysDiv = contentDiv.querySelector('.system-message');
                    if (!sysDiv) {
                        sysDiv = document.createElement('div');
                        sysDiv.className = 'system-message';
                        sysDiv.style.cssText = 'margin: 8px 0; padding: 8px 12px; background: #f3f4f6; border-left: 3px solid #6b7280; border-radius: 4px; color: #374151; font-size: 13px;';
                        const finalDiv = contentDiv.querySelector('.final-response');
                        if (finalDiv) {
                            contentDiv.insertBefore(sysDiv, finalDiv);
                        } else {
                            contentDiv.appendChild(sysDiv);
                        }
                    }
                    sysDiv.textContent = data.content;
                    scrollToBottom();
                }
            }
            break;
        case 'file_tree':
            fileTreeData = data.tree;
            if (explorerCwd) explorerCwd.textContent = data.cwd || '.';
            renderFileTree();
            break;
        case 'file_tree_children':
            _lazyDirCache[data.path] = data.children;
            // Merge into tree data and re-render
            if (fileTreeData) {
                mergeTreeChildren(fileTreeData, data.path, data.children);
                renderFileTree();
            }
            break;
        case 'git_status':
            gitStatusData = data.status;
            renderGitStatus();
            updateChangesBadge();
            break;
        case 'git_diff':
            renderDiffViewer(data.file_path, data.diff);
            break;
        case 'git_log':
            gitCommitLog = data.commits || [];
            updateGitHistoryNav();
            break;
        case 'git_show':
            renderCommitShow(data.commit, data.data);
            break;
        case 'git_branch_list':
            gitBranches = data.branches || {current: '', local: [], remote: []};
            renderBranchSelector();
            break;
        case 'git_checkout_result':
            if (data.success) {
                showToast(`Switched to ${data.branch}`, 'success');
                gitCommitIndex = -1;
                refreshGitData();
            } else {
                showToast(data.message || 'Checkout failed', 'error');
            }
            break;
        case 'context_usage':
            renderContextUsage(data);
            break;
        case 'session_error':
            showToast(data.error || 'Session error', 'error');
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
    // Refresh explorer and git status after each AI response completes
    // to show any files/directories created or modified by the AI.
    // Debounce: don't refresh if called within 2 seconds of last refresh.
    const now = Date.now();
    if (now - _lastRefreshTime > _REFRESH_DEBOUNCE_MS) {
        _lastRefreshTime = now;
        refreshExplorer();
    }
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

// Handle reasoning block (DeepSeek thinking mode)
function handleReasoning(data) {
    const contentDiv = document.getElementById(`content-${currentStreamId}`);
    if (!contentDiv) return;
    
    let reasoningDiv = contentDiv.querySelector('.stream-block.reasoning');
    if (!reasoningDiv) {
        reasoningDiv = document.createElement('div');
        reasoningDiv.className = 'stream-block reasoning';
        reasoningDiv.innerHTML = '<div class="label">Reasoning</div><div class="reasoning-content"></div>';
        const finalDiv = contentDiv.querySelector('.final-response');
        if (finalDiv) {
            contentDiv.insertBefore(reasoningDiv, finalDiv);
        } else {
            contentDiv.appendChild(reasoningDiv);
        }
    }
    
    const reasoningContent = reasoningDiv.querySelector('.reasoning-content');
    reasoningContent.textContent = data.content;
    scrollToBottom();
}

// Handle tool call
function handleToolCall(data) {
    const contentDiv = document.getElementById(`content-${currentStreamId}`);
    if (!contentDiv) return;
    
    const stream = pendingMessages.get(currentStreamId);
    const finalDiv = contentDiv.querySelector('.final-response');
    
    // Extract only the NEW text since the last tool call into a .thinking-response block.
    // Track an offset (stream._extractedLen) so we extract exactly the text that was
    // generated since the LAST extraction — not the full accumulated buffer.
    // Keep stream.content and finalDiv intact so subsequent chunks don't start empty
    // (which caused truncated text like "ilotCode" instead of "查看PilotCode中...").
    if (finalDiv && finalDiv.innerHTML.trim() && stream) {
        const prevLen = stream._extractedLen || 0;
        const newPart = stream.content.slice(prevLen).trim();
        stream._extractedLen = stream.content.length;

        if (newPart) {
            const thinkingDiv = document.createElement('div');
            thinkingDiv.className = 'thinking-response';
            thinkingDiv.innerHTML = renderMarkdown(newPart);
            contentDiv.insertBefore(thinkingDiv, finalDiv);
        }
    }
    
    // Format input parameters in one line
    const inputStr = formatToolInput(data.tool_input);
    
    const toolDiv = document.createElement('div');
    toolDiv.className = 'tool-call';
    toolDiv.id = `tool-${data.tool_name}-${Date.now()}`;
    toolDiv.innerHTML = `
        <div class="tool-header" onclick="toggleTool(this)">
            <span class="icon">[T]</span>
            <span style="white-space: pre-line;">${escapeHtml(data.tool_name)} ${inputStr.replace(/\n/g, '<br>')}</span>
            <span style="margin-left: auto; color: #999;">▼</span>
        </div>
        <div class="tool-content hidden">
            <pre><code>${escapeHtml(JSON.stringify(data.tool_input, null, 2))}</code></pre>
        </div>
    `;
    
    // Insert before final response (which now holds future / final answer content)
    if (finalDiv) {
        contentDiv.insertBefore(toolDiv, finalDiv);
    } else {
        contentDiv.appendChild(toolDiv);
    }
    scrollToBottom();
}

// Format tool input to readable multi-line display
function formatToolInput(input) {
    if (!input || typeof input !== 'object') return '';
    const keyOrder = ['file_path', 'old_string', 'new_string', 'command', 'question', 'code', 'query', 'pattern'];
    const entries = Object.entries(input).sort((a, b) => {
        const ia = keyOrder.indexOf(a[0]);
        const ib = keyOrder.indexOf(b[0]);
        if (ia !== -1 && ib !== -1) return ia - ib;
        if (ia !== -1) return -1;
        if (ib !== -1) return 1;
        return a[0].localeCompare(b[0]);
    });
    return entries.map(([k, v]) => {
        let val = v;
        if (typeof v === 'string') {
            // Show first line only in header, full content in collapsed section
            const firstLine = v.split('\n')[0];
            if (firstLine.length > 60) {
                val = firstLine.substring(0, 57) + '...';
            } else {
                val = firstLine;
            }
        } else if (Array.isArray(v)) {
            val = v.join(', ');
            if (val.length > 40) val = val.substring(0, 37) + '...';
        } else {
            val = String(v);
        }
        return `${k}: ${val}`;
    }).join(' | ');
}

// Handle tool result
function handleToolResult(data) {
    const contentDiv = document.getElementById(`content-${currentStreamId}`);
    if (!contentDiv) return;

    const resultText = data.result || '';
    const isError = data.success === false;  // backend sends "success", not "is_error"
    const toolName = data.tool_name || 'unknown';
    const label = isError ? `Error: ${escapeHtml(toolName)}` : `Result: ${escapeHtml(toolName)}`;
    const icon = isError ? '[E]' : '[R]';

    const wrapper = document.createElement('div');
    wrapper.className = 'tool-result' + (isError ? ' error' : '');
    wrapper.innerHTML = `
        <div class="tool-result-header" onclick="toggleTool(this)">
            <span class="icon">${icon}</span>
            <span>${label}</span>
            <span style="margin-left: auto; color: #999;">▶</span>
        </div>
        <div class="tool-result-content hidden">
            <pre><code>${escapeHtml(resultText)}</code></pre>
        </div>
    `;

    // Insert before final response
    const finalDiv = contentDiv.querySelector('.final-response');
    if (finalDiv) {
        contentDiv.insertBefore(wrapper, finalDiv);
    } else {
        contentDiv.appendChild(wrapper);
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

// Handle user question request
function handleUserQuestionRequest(data) {
    const requestId = data.request_id;
    const question = data.question;
    const options = data.options;
    
    console.log('User question request:', requestId, question);
    
    // Get the current stream content div, or create a new message if stream ended
    let contentDiv = document.getElementById(`content-${currentStreamId}`);
    if (!contentDiv) {
        // Stream may have ended, create a new message container
        const streamDiv = document.createElement('div');
        streamDiv.id = `stream-question-${requestId}`;
        streamDiv.className = 'message';
        streamDiv.innerHTML = `
            <div class="user-query">Waiting for your answer...</div>
            <div class="stream-content" id="content-question-${requestId}"></div>
        `;
        messagesContainer.appendChild(streamDiv);
        contentDiv = document.getElementById(`content-question-${requestId}`);
    }
    
    // Create question block
    const questionDiv = document.createElement('div');
    questionDiv.id = `question-${requestId}`;
    questionDiv.className = 'user-question-request';
    questionDiv.style.cssText = 'margin: 12px 0; padding: 12px; background: #eff6ff; border: 1px solid #3b82f6; border-radius: 6px;';
    
    let optionsHtml = '';
    if (options && options.length > 0) {
        optionsHtml = '<div style="margin: 8px 0;">';
        options.forEach((option, index) => {
            optionsHtml += `<div style="margin: 4px 0; color: #374151;">${index + 1}. ${escapeHtml(option)}</div>`;
        });
        optionsHtml += '</div>';
    }
    
    questionDiv.innerHTML = `
        <div style="font-weight: 600; color: #1e40af; margin-bottom: 8px;">[Q] ${escapeHtml(question)}</div>
        ${optionsHtml}
        <div class="question-actions" style="margin-top: 12px;">
            <input type="text" id="question-input-${requestId}" 
                   style="width: 70%; padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 4px; margin-right: 8px;"
                   placeholder="Your answer..." 
                   onkeypress="if(event.key==='Enter') respondUserQuestion('${requestId}')">
            <button onclick="respondUserQuestion('${requestId}')" 
                    style="padding: 6px 16px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer;">
                Send
            </button>
        </div>
    `;
    
    contentDiv.appendChild(questionDiv);
    scrollToBottom();
    
    // Focus the input
    setTimeout(() => {
        const input = document.getElementById(`question-input-${requestId}`);
        if (input) input.focus();
    }, 100);
}

// Respond to user question
function respondUserQuestion(requestId) {
    const input = document.getElementById(`question-input-${requestId}`);
    if (!input) return;
    
    const response = input.value.trim();
    if (!response) return;
    
    console.log('Responding to question:', requestId, response);
    sendMessage({
        type: 'user_question_response',
        request_id: requestId,
        response: response
    });
    
    // Update UI to show response sent
    const questionDiv = document.getElementById(`question-${requestId}`);
    if (questionDiv) {
        questionDiv.innerHTML = `<div style="color: #166534; font-weight: 500;">✓ Answered: ${escapeHtml(response)}</div>`;
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
    
    // Stop button
    stopBtn.addEventListener('click', () => {
        if (currentStreamId) {
            sendMessage({
                type: 'interrupt'
            });
            showToast('Stopping...', 'info');
        }
    });
    
    // New session
    newSessionBtn.addEventListener('click', () => {
        // Save current session first
        if (currentSessionId) {
            sendMessage({type: 'session_save', name: currentSessionId});
        }
        // Request cwd options then show picker
        sendMessage({type: 'cwd_options'});
    });
    
    // Sidebar toggle
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
    });
    
    // Attach button (placeholder - file upload not implemented yet)
    attachBtn.addEventListener('click', () => {
        showToast('File upload coming soon', 'info');
    });

    // Session search
    const sessionSearch = document.getElementById('sessionSearch');
    if (sessionSearch) {
        sessionSearch.addEventListener('input', () => {
            renderSessionList();
        });
    }

    // Refresh sessions
    const refreshBtn = document.getElementById('refreshSessionsBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            sendMessage({type: 'session_list'});
            showToast('Refreshing sessions...', 'info');
        });
    }

    // Archived section toggle
    const archivedHeader = document.getElementById('archivedHeader');
    if (archivedHeader) {
        archivedHeader.addEventListener('click', () => {
            archivedExpanded = !archivedExpanded;
            const arrow = document.getElementById('archivedArrow');
            const items = document.getElementById('archivedItems');
            if (arrow) arrow.textContent = archivedExpanded ? '▼' : '▶';
            if (items) items.classList.toggle('hidden', !archivedExpanded);
        });
    }

    // Context menu actions
    const contextMenu = document.getElementById('contextMenu');
    if (contextMenu) {
        contextMenu.querySelectorAll('.context-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                console.log('[ContextMenu] clicked action:', item.dataset.action, 'sessionId:', contextMenuSessionId);
                const action = item.dataset.action;
                if (action === 'rename' && contextMenuSessionId) {
                    renameSession(contextMenuSessionId);
                } else if (action === 'archive' && contextMenuSessionId) {
                    const session = sessions.find(s => s.session_id === contextMenuSessionId);
                    const newArchived = !(session && session.archived);
                    sendMessage({type: 'session_archive', session_id: contextMenuSessionId, archived: newArchived});
                } else if (action === 'delete' && contextMenuSessionId) {
                    deleteSession(contextMenuSessionId);
                }
                hideContextMenu();
            });
        });
    }

    // Hide context menu on click elsewhere
    document.addEventListener('click', () => hideContextMenu());

    // CWD Modal events
    if (cwdModalClose) cwdModalClose.addEventListener('click', hideCwdModal);
    if (cwdModalCancel) cwdModalCancel.addEventListener('click', hideCwdModal);
    if (cwdModalConfirm) {
        cwdModalConfirm.addEventListener('click', () => {
            const searchValue = cwdSearch ? cwdSearch.value.trim() : '';
            const cwd = searchValue || selectedCwd || cwdOptionsData.current;
            sendMessage({type: 'session_create', cwd: cwd});
            hideCwdModal();
            clearChatUI();
        });
    }
    if (cwdSearch) {
        cwdSearch.addEventListener('input', () => {
            renderCwdModal();
        });
    }
    if (cwdCurrentItem) {
        cwdCurrentItem.addEventListener('click', () => {
            selectedCwd = cwdOptionsData.current;
            if (cwdSearch) cwdSearch.value = cwdOptionsData.current;
            updateCwdSelectionUI();
        });
    }
    if (cwdModal) {
        cwdModal.addEventListener('click', (e) => {
            if (e.target === cwdModal) hideCwdModal();
        });
    }
}

// Send user message
function sendUserMessage() {
    if (isSending) return;
    const content = messageInput.value.trim();
    if (!content || !isConnected) return;
    
    isSending = true;
    setInputState(true);
    
    const msgId = ++messageId;
    
    sendMessage({
        type: 'query',
        message: content,
        message_id: msgId,
        session_id: currentSessionId
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
        sendBtn.classList.add('hidden');
        stopBtn.classList.remove('hidden');
    } else {
        inputStatus.textContent = 'Ready';
        messageInput.disabled = false;
        messageInput.focus();
        sendBtn.classList.remove('hidden');
        stopBtn.classList.add('hidden');
        isSending = false;
    }
    // Update send button disabled state based on input
    sendBtn.disabled = messageInput.value.trim().length === 0 || !isConnected;
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

    // Extract code blocks first
    const codeBlocks = [];
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const id = codeBlocks.length;
        codeBlocks.push({ lang: lang || 'text', code: code.trim() });
        return `__CODE_BLOCK_${id}__`;
    });

    // Tables: convert markdown pipe tables to HTML tables
    // Process before escapeHtml so <table> tags are preserved.
    const tableBlocks = [];
    text = text.replace(
        /^\|(.+)\|\s*$(?:\n^\|[-:| ]+\|\s*$(?:\n^\|.+\|\s*$)*)?/gm,
        (match) => {
            const id = tableBlocks.length;
            const rows = match.trim().split('\n');
            let html = '<div class="table-wrapper"><table>';

            // First row is header
            if (rows.length >= 1) {
                html += '<thead><tr>';
                const cells = rows[0].split('|').filter(c => c.trim() !== '');
                for (const cell of cells) {
                    html += '<th>' + cell.trim() + '</th>';
                }
                html += '</tr></thead>';
            }

            // Skip separator row (row 1) and process remaining data rows
            if (rows.length >= 3) {
                html += '<tbody>';
                for (let i = 2; i < rows.length; i++) {
                    html += '<tr>';
                    const cells = rows[i].split('|').filter(c => c.trim() !== '');
                    for (const cell of cells) {
                        html += '<td>' + cell.trim() + '</td>';
                    }
                    html += '</tr>';
                }
                html += '</tbody>';
            }

            html += '</table></div>';
            tableBlocks.push(html);
            return `__TABLE_BLOCK_${id}__`;
        }
    );

    // Escape HTML
    text = escapeHtml(text);

    // Headings
    text = text.replace(/^###### (.*?)$/gm, '<h6>$1</h6>');
    text = text.replace(/^##### (.*?)$/gm, '<h5>$1</h5>');
    text = text.replace(/^#### (.*?)$/gm, '<h4>$1</h4>');
    text = text.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
    text = text.replace(/^# (.*?)$/gm, '<h1>$1</h1>');

    // Inline code
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic
    text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Links
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    // Lists: wrap consecutive items in <ul>
    const lines = text.split('\n');
    const processed = [];
    let inList = false;
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const m = line.match(/^(\s*)-\s+(.+)$/);
        if (m) {
            if (!inList) {
                processed.push('<ul>');
                inList = true;
            }
            processed.push(`<li style="margin-left: ${m[1].length * 8}px">${m[2]}</li>`);
        } else {
            if (inList) {
                processed.push('</ul>');
                inList = false;
            }
            processed.push(line);
        }
    }
    if (inList) processed.push('</ul>');
    text = processed.join('\n');

    // Paragraphs: split by blank lines
    const paragraphs = text.split(/\n\n+/);
    const result = [];
    for (const para of paragraphs) {
        const trimmed = para.trim();
        if (!trimmed) continue;        // Skip block-level elements (headings, lists, code block placeholders)
        if (/^<(h[1-6]|ul|ol|blockquote|pre|div|table)\b/.test(trimmed)) {
            result.push(trimmed);
        } else {
            const content = trimmed.replace(/\n/g, '<br>');
            result.push(`<p>${content}</p>`);
        }
    }
    text = result.join('\n');

    // Restore code blocks
    codeBlocks.forEach((block, id) => {
        const escapedCode = block.code.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        text = text.replace(`__CODE_BLOCK_${id}__`, `<div class="code-block">
            <div class="code-header">
                <span>${block.lang}</span>
                <button class="copy-btn" onclick="copyCode(this)">Copy</button>
            </div>
            <pre><code>${escapedCode}</code></pre>
        </div>`);
    });

    // Restore table blocks
    tableBlocks.forEach((html, id) => {
        text = text.replace(`__TABLE_BLOCK_${id}__`, html);
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

// Session management helpers
function clearChatUI() {
    messagesContainer.innerHTML = '';
    messagesContainer.classList.add('hidden');
    welcomeMessage.classList.remove('hidden');
    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendBtn.disabled = true;
    messageId = 0;
    pendingMessages.clear();
    currentStreamId = null;
}

function timeAgo(timestamp) {
    if (!timestamp) return '';
    const now = new Date();
    const then = new Date(timestamp);
    const seconds = Math.floor((now - then) / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months}mo ago`;
    return `${Math.floor(months / 12)}y ago`;
}

function groupSessionsByPath(sessions) {
    const groups = {};
    sessions.forEach(s => {
        const path = s.project_path || 'Unknown';
        if (!groups[path]) groups[path] = [];
        groups[path].push(s);
    });
    return groups;
}

function renderSessionList() {
    const tree = document.getElementById('sessionsTree');
    const archivedItems = document.getElementById('archivedItems');
    const archivedCount = document.getElementById('archivedCount');
    const search = document.getElementById('sessionSearch');
    const query = search ? search.value.trim().toLowerCase() : '';

    tree.innerHTML = '';
    archivedItems.innerHTML = '';

    let filtered = sessions;
    if (query) {
        filtered = sessions.filter(s =>
            (s.name || '').toLowerCase().includes(query) ||
            (s.project_path || '').toLowerCase().includes(query) ||
            (s.summary || '').toLowerCase().includes(query)
        );
    }

    const activeSessions = filtered.filter(s => !s.archived);
    const archivedSessions = filtered.filter(s => s.archived);
    archivedCount.textContent = archivedSessions.length;

    if (activeSessions.length === 0 && archivedSessions.length === 0) {
        tree.innerHTML = '<div style="padding: 12px; color: #999; font-size: 13px;">No sessions</div>';
        return;
    }

    const groups = groupSessionsByPath(activeSessions);
    Object.entries(groups).forEach(([path, items]) => {
        const groupEl = document.createElement('div');
        groupEl.className = 'group';
        const isExpanded = expandedGroups.has(path);

        const header = document.createElement('div');
        header.className = 'group-header';
        header.innerHTML = `
            <span class="group-arrow ${isExpanded ? 'expanded' : ''}">▶</span>
            <span class="group-name">${escapeHtml(path)}</span>
            <span class="group-count">(${items.length})</span>
        `;
        header.addEventListener('click', () => {
            if (expandedGroups.has(path)) expandedGroups.delete(path);
            else expandedGroups.add(path);
            renderSessionList();
        });
        groupEl.appendChild(header);

        if (isExpanded) {
            const itemsContainer = document.createElement('div');
            itemsContainer.className = 'group-items';
            items.forEach(session => {
                const row = createSessionRow(session);
                itemsContainer.appendChild(row);
            });
            groupEl.appendChild(itemsContainer);
        }

        tree.appendChild(groupEl);
    });

    // Render archived sessions
    archivedSessions.forEach(session => {
        archivedItems.appendChild(createSessionRow(session, true));
    });
}

function createSessionRow(session, isArchived) {
    const row = document.createElement('div');
    const isActive = session.session_id === currentSessionId;
    row.className = 'session-row' + (isActive ? ' active' : '');
    row.dataset.sessionId = session.session_id;

    const summary = escapeHtml(session.summary || session.name || session.session_id);
    const ago = timeAgo(session.last_activity || session.updated_at);
    const msgCount = session.message_count || 0;

    row.innerHTML = `
        <div class="session-summary">${summary}</div>
        <div class="session-meta">
            <span>${ago}</span>
            <span>${msgCount} msg${msgCount !== 1 ? 's' : ''}</span>
        </div>
    `;

    row.addEventListener('click', () => switchSession(session.session_id));
    row.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showContextMenu(e, session.session_id);
    });
    return row;
}

function switchSession(sessionId) {
    if (sessionId === currentSessionId) return;
    // Save current before switching
    if (currentSessionId) {
        sendMessage({type: 'session_save', name: currentSessionId});
    }
    sendMessage({type: 'session_load', session_id: sessionId});
}

function deleteSession(sessionId) {
    if (!confirm(`Delete session ${sessionId.slice(0, 16)}?`)) return;
    sendMessage({type: 'session_delete', session_id: sessionId});
}

function renderHistoryMessages(messages) {
    hideWelcome();
    messages.forEach(msg => {
        if (msg.role === 'user') {
            const div = document.createElement('div');
            div.className = 'message';
            div.innerHTML = `<div class="user-query">${escapeHtml(msg.content)}</div><div class="stream-content"></div>`;
            messagesContainer.appendChild(div);
        } else if (msg.role === 'assistant') {
            const div = document.createElement('div');
            div.className = 'message';
            const contentDiv = document.createElement('div');
            contentDiv.className = 'stream-content';
            const finalDiv = document.createElement('div');
            finalDiv.className = 'final-response';
            finalDiv.innerHTML = renderMarkdown(msg.content);
            contentDiv.appendChild(finalDiv);
            div.appendChild(contentDiv);
            messagesContainer.appendChild(div);
        } else if (msg.role === 'tool_use') {
            const div = document.createElement('div');
            div.className = 'message';
            const inputStr = formatToolInput(msg.input);
            div.innerHTML = `
                <div class="tool-call">
                    <div class="tool-header" onclick="toggleTool(this)">
                        <span class="icon">[T]</span>
                        <span style="white-space: pre-line;">${escapeHtml(msg.name)} ${inputStr.replace(/\n/g, '<br>')}</span>
                        <span style="margin-left: auto; color: #999;">▼</span>
                    </div>
                    <div class="tool-content hidden">
                        <pre><code>${escapeHtml(JSON.stringify(msg.input, null, 2))}</code></pre>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(div);
        } else if (msg.role === 'tool_result') {
            const div = document.createElement('div');
            div.className = 'message';
            const content = msg.content || '';
            const isError = msg.is_error;
            const toolName = msg.tool_name || 'unknown';
            const label = isError ? `Error: ${escapeHtml(toolName)}` : `Result: ${escapeHtml(toolName)}`;
            const icon = isError ? '[E]' : '[R]';
            div.innerHTML = `
                <div class="tool-result${isError ? ' error' : ''}">
                    <div class="tool-result-header" onclick="toggleTool(this)">
                        <span class="icon">${icon}</span>
                        <span>${label}</span>
                        <span style="margin-left: auto; color: #999;">▶</span>
                    </div>
                    <div class="tool-result-content hidden">
                        <pre><code>${escapeHtml(content)}</code></pre>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(div);
        } else if (msg.role === 'system') {
            const div = document.createElement('div');
            div.className = 'message';
            div.innerHTML = `<div class="stream-block system">${escapeHtml(msg.content)}</div>`;
            messagesContainer.appendChild(div);
        } else if (msg.role === 'thinking') {
            const div = document.createElement('div');
            div.className = 'message';
            div.innerHTML = `<div class="stream-block thinking">${escapeHtml(msg.content)}</div>`;
            messagesContainer.appendChild(div);
        } else if (msg.role === 'reasoning') {
            const div = document.createElement('div');
            div.className = 'message';
            div.innerHTML = `<div class="stream-block reasoning">${escapeHtml(msg.content)}</div>`;
            messagesContainer.appendChild(div);
        }
    });
    scrollToBottom();
}

function showContextMenu(event, sessionId) {
    console.log('[ContextMenu] show for session:', sessionId);
    contextMenuSessionId = sessionId;
    const menu = document.getElementById('contextMenu');
    if (!menu) { console.error('[ContextMenu] menu element not found'); return; }
    menu.classList.remove('hidden');
    menu.style.left = event.clientX + 'px';
    menu.style.top = event.clientY + 'px';

    const session = sessions.find(s => s.session_id === sessionId);
    const isArchived = session && session.archived;

    const renameItem = menu.querySelector('[data-action="rename"]');
    const archiveItem = menu.querySelector('[data-action="archive"]');

    if (renameItem) renameItem.style.display = isArchived ? 'none' : 'flex';
    if (archiveItem) {
        archiveItem.innerHTML = isArchived
            ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/></svg> Unarchive`
            : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/></svg> Archive`;
    }
}

function hideContextMenu() {
    console.log('[ContextMenu] hide');
    const menu = document.getElementById('contextMenu');
    if (menu) menu.classList.add('hidden');
    contextMenuSessionId = null;
}

function renameSession(sessionId) {
    const session = sessions.find(s => s.session_id === sessionId);
    if (!session) return;
    const newName = prompt('Rename session:', session.name || session.session_id);
    if (newName && newName.trim()) {
        sendMessage({type: 'session_rename', session_id: sessionId, name: newName.trim()});
    }
}

function showCwdModal() {
    if (!cwdModal) return;
    selectedCwd = null;
    cwdModal.classList.remove('hidden');
    if (cwdSearch) cwdSearch.value = '';
    updateCwdSelectionUI();
}

function hideCwdModal() {
    if (!cwdModal) return;
    cwdModal.classList.add('hidden');
}

function renderCwdModal() {
    if (!cwdCurrentPath || !cwdRecentList) return;
    cwdCurrentPath.textContent = cwdOptionsData.current;
    const query = cwdSearch ? cwdSearch.value.trim().toLowerCase() : '';

    let recent = cwdOptionsData.recent;
    if (query) {
        recent = recent.filter(p => p.toLowerCase().includes(query));
    }

    cwdRecentList.innerHTML = '';
    if (recent.length === 0) {
        cwdRecentList.innerHTML = '<div style="padding: 8px; color: #999; font-size: 13px;">No recent directories</div>';
        return;
    }

    recent.forEach(path => {
        const item = document.createElement('div');
        item.className = 'cwd-item' + (selectedCwd === path ? ' selected' : '');
        item.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <span>${escapeHtml(path)}</span>
        `;
        item.addEventListener('click', () => {
            selectedCwd = path;
            if (cwdSearch) cwdSearch.value = path;
            updateCwdSelectionUI();
        });
        cwdRecentList.appendChild(item);
    });

    updateCwdSelectionUI();
}

function updateCwdSelectionUI() {
    if (cwdCurrentItem) {
        cwdCurrentItem.classList.toggle('selected', selectedCwd === cwdOptionsData.current || selectedCwd === null);
    }
    if (cwdRecentList) {
        cwdRecentList.querySelectorAll('.cwd-item').forEach(item => {
            const pathSpan = item.querySelector('span');
            if (pathSpan) {
                item.classList.toggle('selected', selectedCwd === pathSpan.textContent);
            }
        });
    }
}

// ------------------------------------------------------------------
// File Explorer
// ------------------------------------------------------------------

function renderFileTree() {
    if (!fileTree) return;
    if (!fileTreeData || fileTreeData.length === 0) {
        fileTree.innerHTML = '<div class="explorer-empty">No files</div>';
        return;
    }
    fileTree.innerHTML = '';
    fileTreeData.forEach(root => {
        fileTree.appendChild(buildFileNode(root, 0));
    });
}

function buildFileNode(node, level) {
    const isDir = node.type === 'directory';
    const isExpanded = expandedDirs.has(node.path);
    const isSelected = selectedFile === node.path;
    const el = document.createElement('div');

    const row = document.createElement('div');
    row.className = 'file-tree-node' + (isSelected ? ' selected' : '');
    row.style.paddingLeft = (8 + level * 12) + 'px';

    // Icon
    const icon = document.createElement('span');
    icon.className = 'file-tree-icon';
    if (isDir) {
        icon.className += isExpanded ? ' folder-open' : ' folder';
        icon.textContent = isExpanded ? '📂' : '📁';
    } else {
        icon.textContent = '📄';
    }
    row.appendChild(icon);

    // Name
    const name = document.createElement('span');
    name.className = 'file-tree-name';
    name.textContent = node.name;
    row.appendChild(name);

    // Git kind badge
    if (gitStatusData && gitStatusData.is_git && !isDir) {
        const kind = getGitKind(node.path);
        if (kind) {
            const badge = document.createElement('span');
            badge.className = 'file-tree-kind ' + kind;
            badge.textContent = kind === 'add' ? 'A' : kind === 'mod' ? 'M' : kind === 'del' ? 'D' : '';
            row.appendChild(badge);
        }
    }

    el.appendChild(row);

    // Children
    if (isDir && node.children && node.children.length > 0) {
        const children = document.createElement('div');
        children.className = 'file-tree-children' + (isExpanded ? '' : ' hidden');
        node.children.forEach(child => {
            children.appendChild(buildFileNode(child, level + 1));
        });
        el.appendChild(children);

        row.addEventListener('click', (e) => {
            e.stopPropagation();
            if (isExpanded) {
                expandedDirs.delete(node.path);
            } else {
                expandedDirs.add(node.path);
            }
            // Lazy load: if dir has more content not yet loaded, request it
            if (!isExpanded && node.has_more && (!node.children || node.children.length === 0)) {
                sendMessage({type: 'file_tree_expand', path: node.path});
            }
            renderFileTree();
        });
    } else if (!isDir) {
        row.addEventListener('click', (e) => {
            e.stopPropagation();
            selectedFile = node.path;
            renderFileTree();
            requestFileContent(node.path);
        });
    }

    return el;
}

function getGitKind(filePath) {
    if (!gitStatusData || !gitStatusData.files) return null;
    const files = gitStatusData.files;
    // Try relative path matching
    for (const category of ['added', 'modified', 'deleted', 'renamed']) {
        const list = files[category] || [];
        for (const f of list) {
            if (filePath.endsWith(f) || f.endsWith(filePath)) {
                return category === 'added' ? 'add' : category === 'modified' ? 'mod' : category === 'deleted' ? 'del' : 'mod';
            }
        }
    }
    return null;
}

function requestFileContent(filePath) {
    // Insert a reference to the file into the input box
    if (messageInput) {
        const current = messageInput.value;
        const ref = `File: ${filePath}\n`;
        messageInput.value = current + (current ? '\n' : '') + ref;
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';
        messageInput.focus();
    }
}

function renderGitStatus() {
    if (!gitBar) return;
    if (!gitFileList) return;
    if (!gitStatusData || !gitStatusData.is_git) {
        gitBar.innerHTML = '<div class="explorer-empty">Not a git repository</div>';
        gitFileList.innerHTML = '';
        return;
    }
    // If viewing a historical commit, don't overwrite the commit's file list
    if (gitCommitIndex !== -1) {
        // Still update branch/ahead-behind info in the bar
        const s = gitStatusData;
        const branchHtml = `
            <div class="git-branch">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="6" y1="3" x2="6" y2="15"></line>
                    <circle cx="18" cy="6" r="3"></circle>
                    <circle cx="6" cy="18" r="3"></circle>
                    <path d="M18 9a9 9 0 0 1-9 9"></path>
                </svg>
                <span>${escapeHtml(s.branch || 'unknown')}</span>
                ${s.ahead_behind ? `<span style="color:#999;font-size:11px;">${escapeHtml(s.ahead_behind)}</span>` : ''}
            </div>
        `;
        gitBar.innerHTML = branchHtml;
        return;
    }
    const s = gitStatusData;
    const files = s.files || {};
    const modCount = (files.modified || []).length;
    const addCount = (files.added || []).length;
    const delCount = (files.deleted || []).length;
    const untrackedCount = (files.untracked || []).length;

    let statsHtml = '';
    if (addCount) statsHtml += `<span class="git-stat add">+${addCount}</span>`;
    if (modCount) statsHtml += `<span class="git-stat mod">~${modCount}</span>`;
    if (delCount) statsHtml += `<span class="git-stat del">−${delCount}</span>`;
    if (untrackedCount) statsHtml += `<span class="git-stat untracked">?${untrackedCount}</span>`;

    const branchHtml = `
        <div class="git-branch">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="6" y1="3" x2="6" y2="15"></line>
                <circle cx="18" cy="6" r="3"></circle>
                <circle cx="6" cy="18" r="3"></circle>
                <path d="M18 9a9 9 0 0 1-9 9"></path>
            </svg>
            <span>${escapeHtml(s.branch || 'unknown')}</span>
            ${s.ahead_behind ? `<span style="color:#999;font-size:11px;">${escapeHtml(s.ahead_behind)}</span>` : ''}
        </div>
    `;

    gitBar.innerHTML = branchHtml + (statsHtml ? `<div class="git-stats">${statsHtml}</div>` : '');

    // Render file list
    gitFileList.innerHTML = '';
    const categories = [
        { key: 'modified', label: 'Modified', dotClass: 'mod' },
        { key: 'added', label: 'Added', dotClass: 'add' },
        { key: 'deleted', label: 'Deleted', dotClass: 'del' },
        { key: 'untracked', label: 'Untracked', dotClass: 'untracked' },
    ];
    for (const cat of categories) {
        const list = files[cat.key] || [];
        if (list.length === 0) continue;
        const catLabel = document.createElement('div');
        catLabel.className = 'git-file-category';
        catLabel.textContent = `${cat.label} (${list.length})`;
        gitFileList.appendChild(catLabel);
        for (const f of list) {
            const row = document.createElement('div');
            row.className = 'git-file-row' + (selectedDiffFile === f ? ' selected' : '');
            row.innerHTML = `<span class="git-file-dot ${cat.dotClass}"></span><span class="git-file-name">${escapeHtml(f)}</span>`;
            row.addEventListener('click', () => {
                selectedDiffFile = f;
                // Update selection highlight
                gitFileList.querySelectorAll('.git-file-row').forEach(r => r.classList.remove('selected'));
                row.classList.add('selected');
                requestGitDiff(f);
            });
            gitFileList.appendChild(row);
        }
    }
    if (gitFileList.children.length === 0) {
        gitFileList.innerHTML = '<div class="explorer-empty">No changes</div>';
    }
}

function updateChangesBadge() {
    if (!changesBadge) return;
    if (!gitStatusData || !gitStatusData.is_git) {
        changesBadge.classList.add('hidden');
        return;
    }
    const files = gitStatusData.files || {};
    const total = (files.modified || []).length + (files.added || []).length + (files.deleted || []).length + (files.untracked || []).length;
    if (total > 0) {
        changesBadge.textContent = total;
        changesBadge.classList.remove('hidden');
    } else {
        changesBadge.classList.add('hidden');
    }
}

function requestGitDiff(filePath) {
    if (!isConnected) return;
    sendMessage({type: 'git_diff', file_path: filePath});
}

function renderDiffViewer(filePath, diffText) {
    if (!diffViewer || !diffFileName || !diffContent) return;
    diffFileName.textContent = filePath;
    diffContent.innerHTML = '';
    if (!diffText) {
        diffContent.innerHTML = '<div class="diff-empty">No diff available</div>';
        diffViewer.classList.remove('hidden');
        return;
    }
    const lines = diffText.split('\n');
    for (const line of lines) {
        const div = document.createElement('div');
        div.className = 'diff-line';
        if (line.startsWith('+') && !line.startsWith('+++')) {
            div.classList.add('add');
        } else if (line.startsWith('-') && !line.startsWith('---')) {
            div.classList.add('del');
        } else if (line.startsWith('@@')) {
            div.classList.add('hunk');
        } else if (line.startsWith('diff ') || line.startsWith('index ') || line.startsWith('---') || line.startsWith('+++')) {
            div.classList.add('info');
        }
        div.textContent = line;
        diffContent.appendChild(div);
    }
    diffViewer.classList.remove('hidden');
}

function hideDiffViewer() {
    if (diffViewer) diffViewer.classList.add('hidden');
    selectedDiffFile = null;
    if (gitFileList) {
        gitFileList.querySelectorAll('.git-file-row').forEach(r => r.classList.remove('selected'));
    }
}

function mergeTreeChildren(treeData, path, children) {
    // Recursively find the node matching `path` and replace its children
    for (let i = 0; i < treeData.length; i++) {
        const node = treeData[i];
        if (node.path === path) {
            node.children = children;
            node.has_more = false;
            return true;
        }
        if (node.children && node.children.length > 0) {
            if (mergeTreeChildren(node.children, path, children)) {
                return true;
            }
        }
    }
    return false;
}

function refreshExplorer() {
    if (!isConnected) return;
    sendMessage({type: 'file_tree'});
    refreshGitData();
}

function refreshGitData() {
    if (!isConnected) return;
    sendMessage({type: 'git_status'});
    sendMessage({type: 'git_log', max_count: 20});
    sendMessage({type: 'git_branch_list'});
}

function updateGitHistoryNav() {
    if (!gitPrevBtn || !gitNextBtn || !gitLatestBtn || !gitHistoryLabel) return;
    const atHead = gitCommitIndex === -1;
    gitLatestBtn.disabled = atHead;
    gitNextBtn.disabled = atHead;
    gitPrevBtn.disabled = gitCommitLog.length === 0 || gitCommitIndex >= gitCommitLog.length - 1;

    if (atHead) {
        gitHistoryLabel.textContent = 'Working tree';
    } else if (gitCommitIndex >= 0 && gitCommitIndex < gitCommitLog.length) {
        const c = gitCommitLog[gitCommitIndex];
        gitHistoryLabel.textContent = `${c.hash.slice(0, 7)} ${c.message}`;
    } else {
        gitHistoryLabel.textContent = '';
    }
}

function goToCommit(index) {
    if (!gitCommitLog.length) return;
    gitCommitIndex = index;
    updateGitHistoryNav();
    hideDiffViewer();

    if (gitCommitIndex === -1) {
        // Working tree - show current git status
        if (commitInfo) commitInfo.classList.add('hidden');
        if (gitStatusData) renderGitStatus();
    } else if (gitCommitIndex >= 0 && gitCommitIndex < gitCommitLog.length) {
        // Historical commit - fetch show data
        const commit = gitCommitLog[gitCommitIndex].hash;
        sendMessage({type: 'git_show', commit: commit});
    }
}

function renderCommitShow(commitHash, data) {
    if (!commitInfo || !commitHash || !commitMessage || !commitMeta) return;
    const stat = data.stat || '';
    const diff = data.diff || '';

    // Parse commit info from diff header
    let message = '';
    let author = '';
    let date = '';
    const lines = diff.split('\n');
    for (const line of lines) {
        if (line.startsWith('commit ')) {
            // already have hash
        } else if (line.startsWith('Author: ')) {
            author = line.slice(8).trim();
        } else if (line.startsWith('Date: ')) {
            date = line.slice(6).trim();
        } else if (!message && line.trim() && !line.startsWith('diff ') && !line.startsWith('index ')) {
            message = line.trim();
            break;
        }
    }

    commitHash.textContent = commitHash.slice(0, 7);
    commitMessage.textContent = message || '(no message)';
    commitMeta.textContent = author + (date ? ' · ' + date : '');
    commitInfo.classList.remove('hidden');

    // Render changed files from stat
    if (gitFileList) {
        gitFileList.innerHTML = '';
        const statLines = stat.split('\n').filter(l => l.includes('|'));
        if (statLines.length === 0) {
            gitFileList.innerHTML = '<div class="explorer-empty">No file changes</div>';
        } else {
            const catLabel = document.createElement('div');
            catLabel.className = 'git-file-category';
            catLabel.textContent = `Changed files (${statLines.length})`;
            gitFileList.appendChild(catLabel);
            for (const line of statLines) {
                const parts = line.split('|');
                const fname = parts[0].trim();
                const row = document.createElement('div');
                row.className = 'git-file-row';
                row.innerHTML = `<span class="git-file-dot mod"></span><span class="git-file-name">${escapeHtml(fname)}</span>`;
                row.addEventListener('click', () => {
                    gitFileList.querySelectorAll('.git-file-row').forEach(r => r.classList.remove('selected'));
                    row.classList.add('selected');
                    // Show per-file diff within this historical commit
                    sendMessage({type: 'git_diff', file_path: fname, commit: commitHash});
                });
                gitFileList.appendChild(row);
            }
        }
    }

    // Show full commit diff in diff viewer
    renderDiffViewer(commitHash.slice(0, 7), diff);
}

function renderBranchSelector() {
    if (!gitBranchSelect) return;
    gitBranchSelect.innerHTML = '';
    const {current, local, remote} = gitBranches;
    if (local.length === 0 && remote.length === 0) {
        const opt = document.createElement('option');
        opt.textContent = 'No branches';
        gitBranchSelect.appendChild(opt);
        return;
    }
    // Local branches
    if (local.length > 0) {
        const grp = document.createElement('optgroup');
        grp.label = 'Local';
        for (const b of local) {
            const opt = document.createElement('option');
            opt.value = b;
            opt.textContent = b;
            opt.selected = b === current;
            grp.appendChild(opt);
        }
        gitBranchSelect.appendChild(grp);
    }
    // Remote branches
    if (remote.length > 0) {
        const grp = document.createElement('optgroup');
        grp.label = 'Remote';
        for (const b of remote) {
            const opt = document.createElement('option');
            opt.value = b;
            opt.textContent = b;
            grp.appendChild(opt);
        }
        gitBranchSelect.appendChild(grp);
    }
    // Update ahead/behind
    if (gitAheadBehind && gitStatusData && gitStatusData.ahead_behind) {
        gitAheadBehind.textContent = gitStatusData.ahead_behind;
    } else if (gitAheadBehind) {
        gitAheadBehind.textContent = '';
    }
}

function updateToolbarPath(cwd) {
    if (toolbarPathText) {
        toolbarPathText.textContent = cwd || 'PilotCode';
    }
    if (toolbarPath) {
        toolbarPath.title = cwd || '';
    }
}

function fmtK(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'm';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
}

function renderContextUsage(data) {
    if (!contextUsage || !contextPercent || !contextFill) return;
    if (!data || !data.context_window) {
        contextUsage.classList.add('hidden');
        return;
    }
    const pct = data.percentage || 0;
    const tokens = data.token_count || 0;
    const usable = data.usable_context || 1;
    const window = data.context_window || 0;
    const output = data.max_output_tokens || 0;

    contextPercent.textContent = pct.toFixed(1) + '%';
    contextFill.style.width = Math.min(100, pct) + '%';
    contextFill.className = 'context-fill ' + (pct < 50 ? 'low' : pct < 85 ? 'medium' : 'high');

    if (tooltipTokens) tooltipTokens.textContent = fmtK(tokens);
    if (tooltipUsable) tooltipUsable.textContent = fmtK(usable);
    if (tooltipWindow) tooltipWindow.textContent = fmtK(window);
    if (tooltipOutput) tooltipOutput.textContent = fmtK(output);

    contextUsage.classList.remove('hidden');
}

function updateToolbarActiveStates() {
    if (toolbarExplorerBtn) {
        toolbarExplorerBtn.classList.toggle('active', !explorerPanel.classList.contains('collapsed'));
    }
}

// Tab switching
function switchExplorerTab(tab) {
    activeExplorerTab = tab;
    if (tabFiles && tabChanges) {
        tabFiles.classList.toggle('active', tab === 'files');
        tabChanges.classList.toggle('active', tab === 'changes');
    }
    if (filesTabContent && changesTabContent) {
        filesTabContent.classList.toggle('hidden', tab !== 'files');
        changesTabContent.classList.toggle('hidden', tab !== 'changes');
    }
}

if (tabFiles) {
    tabFiles.addEventListener('click', () => switchExplorerTab('files'));
}
if (tabChanges) {
    tabChanges.addEventListener('click', () => switchExplorerTab('changes'));
}

// Diff viewer close
if (diffClose) {
    diffClose.addEventListener('click', hideDiffViewer);
}

// Git history navigation
if (gitPrevBtn) {
    gitPrevBtn.addEventListener('click', () => goToCommit(gitCommitIndex + 1));
}
if (gitNextBtn) {
    gitNextBtn.addEventListener('click', () => goToCommit(Math.max(-1, gitCommitIndex - 1)));
}
if (gitLatestBtn) {
    gitLatestBtn.addEventListener('click', () => goToCommit(-1));
}

// Branch selector
if (gitBranchSelect) {
    gitBranchSelect.addEventListener('change', (e) => {
        const branch = e.target.value;
        if (branch && branch !== gitBranches.current) {
            sendMessage({type: 'git_checkout', branch: branch});
        }
    });
}

function toggleExplorerPanel() {
    if (!explorerPanel) return;
    const isCollapsed = explorerPanel.classList.toggle('collapsed');
    if (isCollapsed) {
        // Save current width and clear inline styles so CSS .collapsed takes effect
        const w = explorerPanel.style.width;
        if (w) {
            explorerPanel.dataset.savedWidth = w;
        }
        explorerPanel.style.width = '';
        explorerPanel.style.minWidth = '';
    } else {
        // Restore saved width
        const saved = explorerPanel.dataset.savedWidth;
        if (saved) {
            explorerPanel.style.width = saved;
            explorerPanel.style.minWidth = saved;
        }
    }
    updateToolbarActiveStates();
}

// Explorer event listeners
if (explorerToggle) {
    explorerToggle.addEventListener('click', toggleExplorerPanel);
}

// Toolbar buttons
if (toolbarExplorerBtn) {
    toolbarExplorerBtn.addEventListener('click', toggleExplorerPanel);
}

// Resizer
let isResizing = false;
let startX = 0;
let startWidth = 0;

if (explorerResizer) {
    explorerResizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        startX = e.clientX;
        startWidth = explorerPanel.offsetWidth;
        explorerPanel.classList.add('resizing');
        explorerResizer.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });
}

document.addEventListener('mousemove', (e) => {
    if (!isResizing || !explorerPanel) return;
    const newWidth = startWidth - (e.clientX - startX);
    const clamped = Math.max(200, Math.min(500, newWidth));
    explorerPanel.style.width = clamped + 'px';
    explorerPanel.style.minWidth = clamped + 'px';
});

document.addEventListener('mouseup', () => {
    if (!isResizing) return;
    isResizing = false;
    if (explorerPanel) explorerPanel.classList.remove('resizing');
    if (explorerResizer) explorerResizer.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    // Save width
    try {
        localStorage.setItem('explorerWidth', explorerPanel.style.width);
    } catch (e) {
        // ignore
    }
});

// Initialize on load
init();
