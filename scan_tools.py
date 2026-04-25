#!/usr/bin/env python3
"""
扫描当前目录，识别所有AI编程相关工具和文件
"""

import os
import glob
from pathlib import Path


def scan_ai_tools():
    """扫描AI编程相关的工具和文件"""
    # 常见的AI编程相关文件模式
    ai_patterns = [
        "requirements*.txt",
        "setup.py",
        "pyproject.toml",
        "Dockerfile*",
        "Makefile",
        "build.gradle",
        "Gemfile",
        "package.json",
        "config*.yaml",
        "config*.yml",
        "config*.json",
        "conf*.py",
        "*.cfg",
        "*.ini",
        "*.toml",
        "Pipfile",
        "poetry.toml",
        "tox.ini",
        "pytest.ini",
        "mypy.ini",
        "*.sh",
        "*.bash",
        "install*.sh",
        "run*.sh",
        "build*.sh",
        "deploy*.sh",
        "start*.sh",
        "test*.py",
        "test_*.py",
        "unit_*.py",
        "integration_*.py",
        "e2e_*.py",
        "conftest.py",
        "Dockerfile*",
        "docker-compose*.yml",
        "docker-compose*.yaml",
        "k8s*.yaml",
        "k8s*.yml",
        ".github/workflows/*",
        ".gitlab-ci.yml",
        ".travis.yml",
        ".circleci/config.yml",
        "Makefile*",
        "fabric*.py",
        "ansible*.yml",
        "terraform*.tf",
        "puppet*.pp",
        "salt*.sls",
        "*.md",
        "*.rst",
        "*.txt",
        "README*",
        "LICENSE*",
        "CONTRIBUTING*",
        "CHANGELOG*",
        "AUTHORS*",
        "NOTICE*",
        "MANIFEST*",
        "pylintrc",
        ".pylintrc",
        ".flake8",
        ".ruff*",
        ".mypy*",
        ".isort*",
        ".bandit*",
        "bandit*.yaml",
        "bandit*.yml",
        ".pre-commit-config.yaml",
        ".pre-commit-config.yml",
        "pre-commit*.py",
        "noxfile.py",
        "tox*.py",
        "setup.cfg",
        "pyproject.toml",
        "mypy.ini",
        "pyrightconfig.json",
        "pyrightconfig.toml",
        "mypy.ini",
        "mypy.toml",
        ".mypy.ini",
        "mypy.config",
        "mypy.config.toml",
        "pyrightconfig.toml",
    ]

    # 识别出的工具和文件
    tools = []

    # 遍历所有文件
    for root, dirs, files in os.walk("."):
        # 过滤掉.git目录
        dirs[:] = [d for d in dirs if d != ".git"]

        for file in files:
            file_path = os.path.join(root, file)

            # 检查文件是否包含AI编程相关的关键词
            ai_keywords = [
                "ai",
                "ml",
                "machine-learning",
                "deep-learning",
                "neural",
                "learning",
                "model",
                "training",
                "data",
                "dataset",
                "pipeline",
                "experiment",
                "framework",
                "torch",
                "tensorflow",
                "keras",
                "sklearn",
                "scikit",
                "pytorch",
                "jupyter",
                "notebook",
                "colab",
                "kaggle",
                "nlp",
                "computer-vision",
                "cv",
                "reinforcement",
                "rl",
                "agent",
                "bot",
                "chatbot",
                "llm",
                "large-language-model",
                "api",
                "service",
            ]

            # 检查文件名是否匹配AI相关模式
            file_lower = file.lower()
            is_ai_file = any(keyword in file_lower for keyword in ai_keywords)

            # 检查文件内容是否包含AI相关关键词
            content_has_ai = False
            if file.endswith(
                (".py", ".sh", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".md", ".txt")
            ):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read().lower()
                        content_has_ai = any(keyword in content for keyword in ai_keywords)
                except Exception:
                    pass  # 忽略无法读取的文件

            # 如果文件名或内容包含AI相关关键词，则加入结果
            if is_ai_file or content_has_ai:
                # 计算相对路径
                rel_path = os.path.relpath(file_path)
                tools.append(
                    {
                        "path": rel_path,
                        "type": "ai_related_file",
                        "description": f"AI/ML related file: {file}",
                    }
                )

    # 检查特定的配置文件
    config_files = [
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-test.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "tox.ini",
        "Pipfile",
        "poetry.toml",
        "conda.yml",
        "environment.yml",
        "Dockerfile",
        "docker-compose.yml",
    ]

    for config_file in config_files:
        if os.path.exists(config_file):
            tools.append(
                {
                    "path": config_file,
                    "type": "configuration_file",
                    "description": f"Configuration file: {config_file}",
                }
            )

    # 检查脚本文件
    script_patterns = ["*.sh", "*.bash", "*.py", "*.pl", "*.rb", "*.js"]
    for pattern in script_patterns:
        for file in glob.glob(pattern):
            if os.path.isfile(file):
                tools.append(
                    {"path": file, "type": "script", "description": f"Script file: {file}"}
                )

    return tools


def main():
    """主函数"""
    tools = scan_ai_tools()

    print("AI编程相关工具和文件识别结果:")
    print("=" * 50)

    # 按类型分组
    tool_types = {}
    for tool in tools:
        tool_type = tool["type"]
        if tool_type not in tool_types:
            tool_types[tool_type] = []
        tool_types[tool_type].append(tool)

    # 打印结果
    for tool_type, tool_list in tool_types.items():
        print(f"\n{tool_type.replace('_', ' ').title()}:")
        for tool in tool_list:
            print(f"  - {tool['path']} - {tool['description']}")

    # 总结统计
    total_tools = len(tools)
    print(f"\n总计: {total_tools} 个文件")

    # 如果文件过多，只显示前100个
    if total_tools > 100:
        print(f"注意: 只显示前100个文件，实际共发现 {total_tools} 个AI相关文件")
        tools = tools[:100]

    return tools


if __name__ == "__main__":
    main()
