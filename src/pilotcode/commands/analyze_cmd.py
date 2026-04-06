"""Advanced code analysis command."""

from pathlib import Path
from .base import CommandHandler, register_command, CommandContext
from ..services.advanced_code_analyzer import get_analyzer


async def analyze_command(args: list[str], context: CommandContext) -> str:
    """Handle /analyze command for deep code analysis."""
    if not args:
        return """Usage: /analyze <path> [options]

Options:
  --arch      显示项目架构概览
  --module    显示模块详细分析
  --class     显示类分析
  --deps      显示依赖关系

Examples:
  /analyze src/                    # 分析整个项目
  /analyze src/pilotcode/tools/    # 分析特定目录
  /analyze src/pilotcode/cli.py    # 分析单个文件
  /analyze --arch                  # 显示架构概览
"""

    analyzer = get_analyzer()
    target = args[0]
    
    # Handle options
    show_arch = '--arch' in args
    show_module = '--module' in args
    show_deps = '--deps' in args
    
    path = Path(context.cwd) / target
    
    if not path.exists():
        return f"Path not found: {target}"

    # If it's a directory, analyze as project
    if path.is_dir():
        if show_arch or len(args) == 1:
            # Generate architecture report
            try:
                report = analyzer.generate_architecture_report(path)
                return report
            except Exception as e:
                return f"Error analyzing project: {e}"
    
    # If it's a file, analyze single file
    if path.is_file():
        if path.suffix != '.py':
            return f"Only Python files are supported: {target}"
        
        module = analyzer.analyze_file(path)
        if not module:
            return f"Could not analyze file: {target}"
        
        output = f"# 文件分析: {target}\n\n"
        
        if module.docstring:
            output += f"## 文档字符串\n{module.docstring}\n\n"
        
        if module.imports:
            output += f"## 导入 ({len(module.imports)} 个)\n"
            for imp in module.imports[:20]:
                if imp['type'] == 'import':
                    output += f"- `import {imp['module']}`"
                    if imp['as']:
                        output += f" as {imp['as']}"
                else:
                    names = ', '.join([n['name'] for n in imp['names']])
                    output += f"- `from {imp['module']} import {names}`"
                output += "\n"
            if len(module.imports) > 20:
                output += f"- ... 和 {len(module.imports) - 20} 个其他导入\n"
            output += "\n"
        
        if module.classes:
            output += f"## 类 ({len(module.classes)} 个)\n\n"
            for cls in module.classes:
                output += f"### {cls.name} (第 {cls.line_number} 行)\n"
                if cls.bases:
                    output += f"**继承**: {', '.join(cls.bases)}\n"
                if cls.docstring:
                    output += f"**文档**: {cls.docstring[:100]}...\n"
                
                if cls.methods:
                    output += f"\n**方法** ({len(cls.methods)} 个):\n"
                    for method in cls.methods:
                        async_flag = "async " if method.is_async else ""
                        args_str = ", ".join(method.args[:4])
                        if len(method.args) > 4:
                            args_str += "..."
                        
                        output += f"- `{async_flag}{method.name}({args_str})`"
                        if method.returns:
                            output += f" -> {method.returns}"
                        output += f" [复杂度: {method.complexity}]"
                        
                        if method.docstring:
                            output += f" - {method.docstring[:50]}..."
                        output += "\n"
                
                if cls.attributes:
                    output += f"\n**属性**: {', '.join(cls.attributes[:10])}\n"
                output += "\n"
        
        if module.functions:
            output += f"## 函数 ({len(module.functions)} 个)\n\n"
            for func in module.functions:
                async_flag = "async " if func.is_async else ""
                args_str = ", ".join(func.args[:4])
                if len(func.args) > 4:
                    args_str += "..."
                
                output += f"### {func.name} (第 {func.line_number} 行)\n"
                output += f"```python\n{async_flag}def {func.name}({args_str})"
                if func.returns:
                    output += f" -> {func.returns}"
                output += "\n```\n"
                
                if func.docstring:
                    output += f"**文档**: {func.docstring}\n"
                
                output += f"**复杂度**: {func.complexity}\n"
                
                if func.decorators:
                    output += f"**装饰器**: {', '.join(func.decorators)}\n"
                
                if func.calls:
                    unique_calls = list(set(func.calls))[:10]
                    output += f"**调用**: {', '.join(unique_calls)}"
                    if len(set(func.calls)) > 10:
                        output += f" 等{len(set(func.calls))}个函数"
                    output += "\n"
                
                output += "\n"
        
        if module.global_vars:
            output += f"## 全局变量 ({len(module.global_vars)} 个)\n"
            output += f"{', '.join(module.global_vars[:20])}\n\n"
        
        return output
    
    return f"Unknown path type: {target}"


register_command(
    CommandHandler(
        name="analyze",
        description="Deep code analysis using AST (not just regex)",
        handler=analyze_command
    )
)
