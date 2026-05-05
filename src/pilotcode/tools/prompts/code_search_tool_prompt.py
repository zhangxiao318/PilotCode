"""CodeSearch tool prompts."""

# =============================================================================


def get_simple_prompt() -> str:
    """Get basic CodeSearch tool description."""
    return """## CodeSearch Tool

Intelligent code search using symbols, semantics, or regex.

**Parameters:**
- query: Search query (symbol name, semantic concept, or regex)
- search_type: "symbol", "semantic", or "regex" (default: semantic)
- scope: Files to search in (default: entire project)

**search_type options:**
- symbol: Exact symbol names (class, function, variable)
- semantic: Concepts and meaning
- regex: Regular expression matching

**Example:**
- `CodeSearch(query="FilePathField", search_type="symbol")`
- `CodeSearch(query="media merge conflict", search_type="semantic")`"""


def get_large_codebase_guidance() -> str:
    """Get guidance for large codebases."""
    return """## Large codebases (> ~50 files)

**ALWAYS start with CodeSearch:**
1. Use CodeSearch with search_type="symbol" for exact names
2. Use CodeSearch with search_type="semantic" for concepts
3. Only fallback to Glob/Grep if CodeSearch returns nothing useful"""


def get_prompt() -> str:
    """Get complete prompt."""
    return "\n\n".join([get_simple_prompt(), get_large_codebase_guidance()])


TOOL_NAME = "CodeSearch"
