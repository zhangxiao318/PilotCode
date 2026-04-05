"""Services for PilotCode."""

from .mcp_client import MCPClient, MCPConfig, MCPServerConnection
from .mcp_config_manager import (
    MCPConfigManager,
    ConfigScope,
    MCPServerEntry,
    get_mcp_config_manager,
)
from .file_metadata_cache import (
    FileMetadataCache,
    FileMetadata,
    LineEndingType,
    detect_file_encoding,
    detect_line_endings,
    get_file_metadata_cache,
    clear_file_metadata_cache,
    LRUCache,
    cached_file_operation,
)
from .ai_security import (
    SecurityAnalysis,
    RiskLevel,
    get_command_security_analysis,
    extract_command_prefix,
    split_command,
    clear_security_cache,
)
from .result_truncation import (
    TruncatedResult,
    TruncationConfig,
    truncate_file_list,
    truncate_text_content,
    truncate_search_results,
    truncate_directory_listing,
)
from .tool_cache import ToolCache, get_tool_cache
from .token_estimation import TokenEstimator, get_token_estimator, estimate_tokens
from .context_compression import ContextCompressor, PriorityBasedCompressor, get_context_compressor
from .tool_orchestrator import ToolOrchestrator, ExecutionMode, get_tool_orchestrator
from .binary_feedback import (
    BinaryFeedbackTester,
    BinaryFeedbackAnalysis,
    FeedbackResult,
    StabilityLevel,
    get_binary_feedback_tester,
    is_binary_feedback_enabled,
)
from .conversation_fork import (
    ConversationForker,
    ConversationSummarizer,
    ForkResult,
    ConversationSummary,
    get_conversation_forker,
    fork_current_conversation,
)
from .update_checker import (
    UpdateChecker,
    UpdateCheckResult,
    UpdateInfo,
    UpdateStatus,
    check_for_updates,
    should_check_updates,
)
from .file_watcher import (
    FileWatcher,
    FileChangeEvent,
    FileChangeType,
    WatcherConfig,
    get_file_watcher,
    watch_path,
)
from .code_index import (
    CodeIndexer,
    CodeIndex,
    Symbol,
    get_code_indexer,
)
from .snapshot import (
    SnapshotManager,
    SnapshotInfo,
    SnapshotDiff,
    get_snapshot_manager,
)
from .task_queue import (
    BackgroundTaskQueue,
    Task,
    TaskResult,
    TaskStatus,
    get_task_queue,
    run_in_background,
)
from .session_persistence import (
    SessionPersistence,
    SessionMetadata,
    get_session_persistence,
    save_session,
    load_session,
    list_sessions,
)
from .team_manager import (
    TeamManager,
    Team,
    Agent,
    AgentStatus,
    get_team_manager,
    create_team,
    spawn_agent,
)
from .error_recovery import (
    RetryHandler,
    RetryConfig,
    RetryResult,
    CircuitBreaker,
    ErrorClassifier,
    ErrorCategory,
    get_retry_handler,
    with_retry,
)
from .intelligent_compact import (
    IntelligentContextCompactor,
    CompactionResult,
    CompactConfig,
    ToolResultSummary,
    get_intelligent_compactor,
)
from .risk_assessment import (
    ToolRiskAnalyzer,
    CommandRiskAnalyzer,
    RiskLevel,
    RiskAssessment,
    get_risk_analyzer,
)
from .prompt_cache import (
    PromptCache,
    CacheEntry,
    CacheStats,
    CacheAwareMessageBuilder,
    get_prompt_cache,
    clear_prompt_cache,
)
from .tool_sandbox import (
    ToolSandbox,
    SandboxConfig,
    SandboxLevel,
    SandboxResult,
    CommandAnalyzer,
    get_tool_sandbox,
    analyze_command_safety,
    is_command_safe,
)
from .embedding_service import (
    EmbeddingService,
    EmbeddingVector,
    SearchResult,
    EmbeddingStats,
    SimpleEmbeddingProvider,
    VectorStore,
    get_embedding_service,
    clear_embedding_service,
)


__all__ = [
    # MCP
    "MCPClient",
    "MCPConfig",
    "MCPServerConnection",
    "MCPConfigManager",
    "ConfigScope",
    "MCPServerEntry",
    "get_mcp_config_manager",
    # File metadata cache
    "FileMetadataCache",
    "FileMetadata",
    "LineEndingType",
    "detect_file_encoding",
    "detect_line_endings",
    "get_file_metadata_cache",
    "clear_file_metadata_cache",
    "LRUCache",
    "cached_file_operation",
    # AI Security
    "SecurityAnalysis",
    "RiskLevel",
    "get_command_security_analysis",
    "extract_command_prefix",
    "split_command",
    "clear_security_cache",
    # Result truncation
    "TruncatedResult",
    "TruncationConfig",
    "truncate_file_list",
    "truncate_text_content",
    "truncate_search_results",
    "truncate_directory_listing",
    # Existing services
    "ToolCache",
    "get_tool_cache",
    "TokenEstimator",
    "get_token_estimator",
    "estimate_tokens",
    "ContextCompressor",
    "PriorityBasedCompressor",
    "get_context_compressor",
    "ToolOrchestrator",
    "ExecutionMode",
    "get_tool_orchestrator",
    # Binary feedback
    "BinaryFeedbackTester",
    "BinaryFeedbackAnalysis",
    "FeedbackResult",
    "StabilityLevel",
    "get_binary_feedback_tester",
    "is_binary_feedback_enabled",
    # Conversation fork
    "ConversationForker",
    "ConversationSummarizer",
    "ForkResult",
    "ConversationSummary",
    "get_conversation_forker",
    "fork_current_conversation",
    # Update checker
    "UpdateChecker",
    "UpdateCheckResult",
    "UpdateInfo",
    "UpdateStatus",
    "check_for_updates",
    "should_check_updates",
    # File watcher
    "FileWatcher",
    "FileChangeEvent",
    "FileChangeType",
    "WatcherConfig",
    "get_file_watcher",
    "watch_path",
    # Code indexing
    "CodeIndexer",
    "CodeIndex",
    "Symbol",
    "get_code_indexer",
    # Snapshot
    "SnapshotManager",
    "SnapshotInfo",
    "SnapshotDiff",
    "get_snapshot_manager",
    # Task queue
    "BackgroundTaskQueue",
    "Task",
    "TaskResult",
    "TaskStatus",
    "get_task_queue",
    "run_in_background",
    # Session persistence
    "SessionPersistence",
    "SessionMetadata",
    "get_session_persistence",
    "save_session",
    "load_session",
    "list_sessions",
    # Team management
    "TeamManager",
    "Team",
    "Agent",
    "AgentStatus",
    "get_team_manager",
    "create_team",
    "spawn_agent",
    # Error recovery
    "RetryHandler",
    "RetryConfig",
    "RetryResult",
    "CircuitBreaker",
    "ErrorClassifier",
    "ErrorCategory",
    "get_retry_handler",
    "with_retry",
    # Intelligent compaction
    "IntelligentContextCompactor",
    "CompactionResult",
    "CompactConfig",
    "ToolResultSummary",
    "get_intelligent_compactor",
    # Risk assessment
    "ToolRiskAnalyzer",
    "CommandRiskAnalyzer",
    "RiskLevel",
    "RiskAssessment",
    "get_risk_analyzer",
    # Prompt cache
    "PromptCache",
    "CacheEntry",
    "CacheStats",
    "CacheAwareMessageBuilder",
    "get_prompt_cache",
    "clear_prompt_cache",
    # Tool sandbox
    "ToolSandbox",
    "SandboxConfig",
    "SandboxLevel",
    "SandboxResult",
    "CommandAnalyzer",
    "get_tool_sandbox",
    "analyze_command_safety",
    "is_command_safe",
    # Embedding service
    "EmbeddingService",
    "EmbeddingVector",
    "SearchResult",
    "EmbeddingStats",
    "SimpleEmbeddingProvider",
    "VectorStore",
    "get_embedding_service",
    "clear_embedding_service",
]
