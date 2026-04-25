#!/usr/bin/env python3
"""
任务依赖分析工具
分析任务依赖管理和编排方面的不足
"""

import networkx as nx
import yaml
from collections import defaultdict
from typing import Dict, List, Set, Any


class TaskDependencyAnalyzer:
    """任务依赖分析器"""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.task_dependencies = defaultdict(list)
        self.task_sequence = []

    def analyze_task_dependencies(self, task_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析任务依赖关系

        Args:
            task_list: 任务列表，每个任务包含id、description、depends_on等字段

        Returns:
            依赖分析结果
        """
        # 构建依赖图
        for task in task_list:
            task_id = task.get("id")
            depends_on = task.get("depends_on", [])

            # 添加节点
            self.graph.add_node(task_id, description=task.get("description", ""))

            # 添加依赖边
            for dep in depends_on:
                self.graph.add_edge(dep, task_id)

        # 检查循环依赖
        try:
            cycles = list(nx.simple_cycles(self.graph))
        except:
            cycles = []

        # 获取任务执行顺序
        try:
            # 拓扑排序获取执行顺序
            execution_order = list(nx.topological_sort(self.graph))
        except:
            execution_order = []

        # 分析依赖缺陷
        defects = self._identify_defects()

        return {
            "cycles": cycles,
            "execution_order": execution_order,
            "defects": defects,
            "dependency_graph": self._export_graph(),
            "task_count": len(task_list),
        }

    def _identify_defects(self) -> List[Dict[str, str]]:
        """识别依赖管理缺陷"""
        defects = []

        # 1. 检查未定义的依赖
        all_nodes = set(self.graph.nodes())
        for node in all_nodes:
            predecessors = set(self.graph.predecessors(node))
            for dep in predecessors:
                if dep not in all_nodes:
                    defects.append(
                        {
                            "type": "undefined_dependency",
                            "message": f"Task {node} depends on undefined task {dep}",
                        }
                    )

        # 2. 检查循环依赖
        try:
            cycles = list(nx.simple_cycles(self.graph))
            for cycle in cycles:
                defects.append(
                    {
                        "type": "circular_dependency",
                        "message": f"Circular dependency detected: {cycle}",
                    }
                )
        except:
            pass

        # 3. 检查孤立任务（无依赖但无前置任务）
        for node in self.graph.nodes():
            if self.graph.in_degree(node) == 0 and self.graph.out_degree(node) == 0:
                defects.append(
                    {
                        "type": "isolated_task",
                        "message": f"Isolated task with no dependencies or dependents: {node}",
                    }
                )

        return defects

    def _export_graph(self) -> Dict[str, Any]:
        """导出图结构"""
        return {
            "nodes": list(self.graph.nodes()),
            "edges": list(self.graph.edges()),
            "adjacency": dict(self.graph.adjacency()),
        }


def main():
    """主函数 - 演示分析过程"""

    # 示例任务数据（模拟实际任务配置）
    sample_tasks = [
        {"id": "task_1", "description": "数据采集", "depends_on": []},
        {"id": "task_2", "description": "数据处理", "depends_on": ["task_1"]},
        {"id": "task_3", "description": "数据分析", "depends_on": ["task_2"]},
        {"id": "task_4", "description": "报告生成", "depends_on": ["task_2", "task_3"]},
        {"id": "task_5", "description": "数据验证", "depends_on": ["task_1"]},
    ]

    # 创建分析器并分析
    analyzer = TaskDependencyAnalyzer()
    analysis_result = analyzer.analyze_task_dependencies(sample_tasks)

    # 输出分析结果
    print("=== 任务依赖分析报告 ===")
    print(f"任务总数: {analysis_result['task_count']}")
    print(f"执行顺序: {analysis_result['execution_order']}")

    if analysis_result["cycles"]:
        print("❌ 发现循环依赖:")
        for cycle in analysis_result["cycles"]:
            print(f"  - {cycle}")
    else:
        print("✅ 无循环依赖")

    if analysis_result["defects"]:
        print("\n⚠️  依赖管理缺陷:")
        for defect in analysis_result["defects"]:
            print(f"  - [{defect['type']}] {defect['message']}")
    else:
        print("\n✅ 无发现依赖管理缺陷")

    # 生成YAML报告
    report = {
        "analysis": {
            "task_count": analysis_result["task_count"],
            "execution_order": analysis_result["execution_order"],
            "cycles": analysis_result["cycles"],
            "defects": analysis_result["defects"],
        },
        "recommendations": generate_recommendations(analysis_result),
    }

    print("\n=== YAML分析报告 ===")
    print(yaml.dump(report, default_flow_style=False, allow_unicode=True))


def generate_recommendations(analysis_result: Dict[str, Any]) -> List[str]:
    """基于分析结果生成改进建议"""
    recommendations = []

    if analysis_result["defects"]:
        recommendations.append("1. 修复检测到的依赖缺陷")

    if analysis_result["cycles"]:
        recommendations.append("2. 消除循环依赖，重新设计任务依赖关系")

    recommendations.extend(
        [
            "3. 实现任务依赖验证机制",
            "4. 增加任务执行顺序自动推导能力",
            "5. 提供可视化依赖图展示",
            "6. 实现依赖完整性检查",
            "7. 添加任务依赖冲突检测",
            "8. 支持动态依赖关系调整",
        ]
    )

    return recommendations


if __name__ == "__main__":
    main()
