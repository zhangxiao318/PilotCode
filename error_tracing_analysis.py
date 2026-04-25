#!/usr/bin/env python3
"""
错误溯源分析工具
分析工具在错误溯源和根本原因分析方面的缺陷
"""

import networkx as nx
from collections import defaultdict
import traceback
import sys
from typing import Dict, List, Any, Set


class ErrorTracingAnalyzer:
    """错误溯源分析器"""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.dependency_graph = nx.DiGraph()
        self.error_nodes = set()
        self.error_context = defaultdict(list)

    def analyze_error_tracing_mechanism(self, error_log: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析错误溯源机制

        Args:
            error_log: 错误日志列表，包含错误信息、调用栈、依赖关系等

        Returns:
            错误溯源分析结果
        """
        # 构建错误依赖图
        self._build_error_dependency_graph(error_log)

        # 识别溯源缺陷
        defects = self._identify_tracing_defects()

        # 分析影响范围
        impact_analysis = self._analyze_impact_scope()

        return {
            "defects": defects,
            "impact_analysis": impact_analysis,
            "error_nodes": list(self.error_nodes),
            "dependency_graph": self._export_dependency_graph(),
        }

    def _build_error_dependency_graph(self, error_log: List[Dict[str, Any]]):
        """构建错误依赖图"""
        # 添加错误节点
        for error in error_log:
            error_id = error.get("error_id", str(hash(str(error))))
            self.error_nodes.add(error_id)
            self.graph.add_node(error_id, error_info=error)

            # 添加依赖关系
            depends_on = error.get("depends_on", [])
            for dep in depends_on:
                self.graph.add_edge(dep, error_id)

            # 添加调用栈关系
            call_stack = error.get("call_stack", [])
            if call_stack and len(call_stack) > 1:
                for i in range(len(call_stack) - 1):
                    caller = call_stack[i]
                    callee = call_stack[i + 1]
                    self.graph.add_edge(caller, callee)

    def _identify_tracing_defects(self) -> List[Dict[str, str]]:
        """识别溯源机制缺陷"""
        defects = []

        # 1. 检查错误信息完整性
        for node in self.graph.nodes():
            error_info = self.graph.nodes[node].get("error_info", {})
            if not error_info.get("error_type"):
                defects.append(
                    {
                        "type": "incomplete_error_info",
                        "message": f"错误信息不完整: {node}",
                        "severity": "high",
                    }
                )

        # 2. 检查循环依赖（错误处理中的循环）
        try:
            cycles = list(nx.simple_cycles(self.graph))
            for cycle in cycles:
                defects.append(
                    {
                        "type": "circular_error_dependency",
                        "message": f"检测到错误依赖循环: {cycle}",
                        "severity": "high",
                    }
                )
        except:
            pass

        # 3. 检查未定义的错误依赖
        all_nodes = set(self.graph.nodes())
        for node in all_nodes:
            predecessors = set(self.graph.predecessors(node))
            for dep in predecessors:
                if dep not in all_nodes:
                    defects.append(
                        {
                            "type": "undefined_error_dependency",
                            "message": f"错误 {node} 依赖未定义的错误 {dep}",
                            "severity": "medium",
                        }
                    )

        # 4. 检查孤立错误节点
        for node in self.graph.nodes():
            if self.graph.in_degree(node) == 0 and self.graph.out_degree(node) == 0:
                defects.append(
                    {
                        "type": "isolated_error_node",
                        "message": f"孤立错误节点: {node}",
                        "severity": "low",
                    }
                )

        return defects

    def _analyze_impact_scope(self) -> Dict[str, Any]:
        """分析错误影响范围"""
        impact_analysis = {
            "affected_components": [],
            "cascade_effects": [],
            "root_causes": [],
            "severity_levels": defaultdict(int),
        }

        # 分析影响范围
        for node in self.graph.nodes():
            error_info = self.graph.nodes[node].get("error_info", {})
            severity = error_info.get("severity", "medium")
            impact_analysis["severity_levels"][severity] += 1

            # 分析影响的组件
            component = error_info.get("component", "unknown")
            if component not in impact_analysis["affected_components"]:
                impact_analysis["affected_components"].append(component)

        # 分析级联效应
        for node in self.graph.nodes():
            if self.graph.out_degree(node) > 0:
                dependents = list(self.graph.successors(node))
                if len(dependents) > 1:
                    impact_analysis["cascade_effects"].append(
                        {"source": node, "affected": dependents, "count": len(dependents)}
                    )

        return impact_analysis

    def _export_dependency_graph(self) -> Dict[str, Any]:
        """导出依赖图"""
        return {
            "nodes": list(self.graph.nodes()),
            "edges": list(self.graph.edges()),
            "adjacency": dict(self.graph.adjacency()),
        }

    def generate_recommendations(self, analysis_result: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        recommendations = []

        # 基于分析结果生成建议
        if analysis_result.get("defects"):
            recommendations.append("1. 改进错误信息记录，确保包含完整错误类型和上下文")

        if analysis_result.get("impact_analysis", {}).get("cascade_effects"):
            recommendations.append("2. 实现错误传播分析机制，识别级联故障")

        if analysis_result.get("impact_analysis", {}).get("affected_components"):
            recommendations.append("3. 增强组件依赖关系追踪，提供更清晰的影响范围分析")

        recommendations.extend(
            [
                "4. 实现错误分类和优先级评估机制",
                "5. 增加错误溯源的可视化展示",
                "6. 提供根本原因分析工具",
                "7. 建立错误模式识别和预测机制",
                "8. 实现错误处理策略的动态调整",
                "9. 增强错误日志的结构化存储和查询能力",
                "10. 提供错误修复建议和回滚策略",
            ]
        )

        return recommendations


def main():
    """主函数 - 演示错误溯源分析"""

    # 模拟错误日志
    sample_errors = [
        {
            "error_id": "err_001",
            "error_type": "FileNotFoundError",
            "message": "无法找到配置文件",
            "component": "config_loader",
            "severity": "high",
            "depends_on": [],
            "call_stack": ["load_config", "main"],
            "timestamp": "2023-01-01T10:00:00Z",
        },
        {
            "error_id": "err_002",
            "error_type": "ValueError",
            "message": "配置值无效",
            "component": "config_validator",
            "severity": "medium",
            "depends_on": ["err_001"],
            "call_stack": ["validate_config", "load_config"],
            "timestamp": "2023-01-01T10:00:05Z",
        },
        {
            "error_id": "err_003",
            "error_type": "RuntimeError",
            "message": "配置验证失败",
            "component": "main_app",
            "severity": "high",
            "depends_on": ["err_002"],
            "call_stack": ["main", "validate_config"],
            "timestamp": "2023-01-01T10:00:10Z",
        },
    ]

    # 创建分析器并分析
    analyzer = ErrorTracingAnalyzer()
    analysis_result = analyzer.analyze_error_tracing_mechanism(sample_errors)

    # 输出分析结果
    print("=== 错误溯源分析报告 ===")
    print(f"错误节点数: {len(analysis_result['error_nodes'])}")

    if analysis_result["defects"]:
        print("\n⚠️  溯源机制缺陷:")
        for defect in analysis_result["defects"]:
            print(f"  - [{defect['type']}] {defect['message']} (严重程度: {defect['severity']})")
    else:
        print("\n✅ 未发现溯源机制缺陷")

    if analysis_result["impact_analysis"]["affected_components"]:
        print(
            f"\n受影响组件: {', '.join(analysis_result['impact_analysis']['affected_components'])}"
        )

    if analysis_result["impact_analysis"]["cascade_effects"]:
        print("\n级联效应:")
        for effect in analysis_result["impact_analysis"]["cascade_effects"]:
            print(f"  - {effect['source']} 影响 {effect['count']} 个组件")

    # 生成改进建议
    recommendations = analyzer.generate_recommendations(analysis_result)
    print("\n=== 改进建议 ===")
    for rec in recommendations:
        print(f"  {rec}")


if __name__ == "__main__":
    main()
