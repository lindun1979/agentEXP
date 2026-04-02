#!/usr/bin/env python3
"""
混合记忆检索适配层
包装 memory-core 的检索逻辑，提供中文查询改写、干扰意图过滤、混合检索功能
"""

import json
import re
import os
import subprocess
import time
from typing import List, Dict, Any, Optional

class HybridMemoryAdapter:
    """
    混合记忆检索适配器
    
    工作流程：
    1. 加载配置（改写规则、干扰模式、检索策略）
    2. 接收用户查询
    3. 干扰意图检测 → 若匹配则直接返回空
    4. 查询改写 → 生成关键词变体
    5. 混合检索 → search优先，vsearch兜底
    6. 结果合并与返回
    """
    
    def __init__(self, config_dir: str = None, agent: str = "main"):
        """
        初始化适配器
        
        Args:
            config_dir: 配置文件目录，默认 ~/.openclaw/memory/
            agent: 代理名称（main 或 OpCoder），用于确定索引路径
        """
        if config_dir is None:
            config_dir = os.path.expanduser("~/.openclaw/memory/")
        
        self.config_dir = config_dir
        self.agent = agent
        
        # 加载配置文件
        self.rewrite_map = self._load_config("chinese_rewrite_map.json")
        self.noise_patterns = self._load_config("noise_intent_patterns.json")
        self.search_config = self._load_config("hybrid_search_config.json")
        
        # 设置QMD环境变量
        self.env = os.environ.copy()
        self.env['XDG_CONFIG_HOME'] = os.path.expanduser(f'~/.openclaw/agents/{agent}/qmd/xdg-config')
        self.env['XDG_CACHE_HOME'] = os.path.expanduser(f'~/.openclaw/agents/{agent}/qmd/xdg-cache')
        
        # 性能统计
        self.metrics = {
            'total_queries': 0,
            'noise_filtered': 0,
            'avg_latency': 0.0,
            'last_query_time': None
        }
    
    def _load_config(self, filename: str) -> Dict[str, Any]:
        """加载JSON配置文件"""
        path = os.path.join(self.config_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"警告: 配置文件 {path} 未找到，使用空配置")
            return {}
        except json.JSONDecodeError as e:
            print(f"错误: 配置文件 {path} JSON格式错误: {e}")
            return {}
    
    def detect_noise_intent(self, query: str) -> bool:
        """检测干扰意图"""
        patterns = self.noise_patterns.get('patterns', [])
        matching_mode = self.noise_patterns.get('matching_mode', 'case_insensitive')
        flags = re.IGNORECASE if matching_mode == 'case_insensitive' else 0
        
        # 检查排除模式（优先级最高）
        exclude_patterns = [p for p in patterns if p.get('action') == 'exclude']
        for pattern in exclude_patterns:
            if re.search(pattern['regex'], query, flags):
                return False  # 匹配排除模式，不视为干扰
        
        # 检查短路模式
        short_circuit_patterns = [p for p in patterns if p.get('action') == 'short_circuit']
        for pattern in short_circuit_patterns:
            if re.search(pattern['regex'], query, flags):
                return True  # 匹配干扰模式
        
        return False
    
    def rewrite_query(self, original: str) -> str:
        """应用查询改写规则"""
        rules = self.rewrite_map.get('rules', [])
        fallback = self.rewrite_map.get('fallback_strategy', 'keep_original')
        
        for rule in rules:
            pattern = rule['pattern']
            rewrite = rule['rewrite']
            if pattern in original:
                return rewrite
        
        # 回退策略
        if fallback == 'keep_original':
            return original
        elif fallback == 'split_chinese':
            # 简单的中文分词：按字符分割并去重
            chars = list(set(original))
            return ' '.join(chars)
        else:
            return original
    
    def run_qmd_search(self, query: str, mode: str = 'search', timeout: int = 10) -> List[Dict]:
        """执行QMD搜索"""
        try:
            cmd = ['qmd', mode, query, '--json', '-n', '3', '-c', 'memory-dir-main']
            result = subprocess.run(
                cmd, 
                env=self.env, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            
            if not result.stdout.strip().startswith('['):
                return []
            
            return json.loads(result.stdout.strip())
        except subprocess.TimeoutExpired:
            return []
        except Exception as e:
            print(f"QMD搜索错误 ({mode}): {e}")
            return []
    
    def search(self, query: str) -> Dict[str, Any]:
        """
        主检索接口
        
        Args:
            query: 用户查询字符串
            
        Returns:
            包含结果和元数据的字典
        """
        start_time = time.time()
        self.metrics['total_queries'] += 1
        
        # 1. 干扰意图检测
        is_noise = self.detect_noise_intent(query)
        if is_noise:
            self.metrics['noise_filtered'] += 1
            return {
                'query': query,
                'is_noise': True,
                'results': [],
                'num_results': 0,
                'latency': time.time() - start_time,
                'stages_used': ['noise_filter'],
                'message': '干扰意图已过滤'
            }
        
        # 2. 查询改写
        rewritten = self.rewrite_query(query)
        
        # 3. 关键词搜索（原查询）
        results_original = self.run_qmd_search(query, 'search', timeout=10)
        
        # 4. 关键词搜索（改写后查询）
        results_rewritten = []
        if rewritten != query:
            results_rewritten = self.run_qmd_search(rewritten, 'search', timeout=10)
        
        # 合并结果（去重）
        merged_results = []
        seen_paths = set()
        
        for result in results_original + results_rewritten:
            path = result.get('path') or result.get('filepath') or result.get('file')
            if path and path not in seen_paths:
                merged_results.append(result)
                seen_paths.add(path)
        
        # 5. 向量搜索兜底（如果结果不足）
        stages_used = ['search_original']
        if rewritten != query:
            stages_used.append('search_rewritten')
        
        if len(merged_results) < 1:
            vector_results = self.run_qmd_search(query, 'vsearch', timeout=15)
            stages_used.append('vsearch_fallback')
            
            for result in vector_results:
                path = result.get('path') or result.get('filepath') or result.get('file')
                if path and path not in seen_paths:
                    merged_results.append(result)
                    seen_paths.add(path)
        
        latency = time.time() - start_time
        self.metrics['avg_latency'] = (
            (self.metrics['avg_latency'] * (self.metrics['total_queries'] - 1) + latency) 
            / self.metrics['total_queries']
        )
        
        return {
            'query': query,
            'is_noise': False,
            'results': merged_results,
            'num_results': len(merged_results),
            'latency': latency,
            'stages_used': stages_used,
            'rewritten_query': rewritten if rewritten != query else None,
            'top_result': merged_results[0].get('path') if merged_results else None
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        return self.metrics.copy()
    
    def reset_metrics(self) -> None:
        """重置性能指标"""
        self.metrics = {
            'total_queries': 0,
            'noise_filtered': 0,
            'avg_latency': 0.0,
            'last_query_time': None
        }


def test_adapter():
    """适配器测试函数"""
    adapter = HybridMemoryAdapter()
    
    # 测试查询
    test_queries = [
        ("OpenClaw私有记忆系统位置", "相关查询"),
        ("今天天气怎么样", "干扰查询"),
        ("冬哥方法论 核心原则", "相关查询"),
        ("Java 并发面试题", "干扰查询"),
        ("STATE 下一步", "相关查询"),
    ]
    
    print("适配器测试开始...")
    print("=" * 60)
    
    for query, category in test_queries:
        print(f"\n查询: {query} ({category})")
        result = adapter.search(query)
        
        if result['is_noise']:
            print(f"  状态: 干扰过滤")
        else:
            print(f"  状态: 找到 {result['num_results']} 个结果")
            print(f"  延迟: {result['latency']:.2f}s")
            print(f"  阶段: {', '.join(result['stages_used'])}")
            if result.get('rewritten_query'):
                print(f"  改写: {result['rewritten_query']}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print(f"总查询数: {adapter.metrics['total_queries']}")
    print(f"干扰过滤数: {adapter.metrics['noise_filtered']}")
    print(f"平均延迟: {adapter.metrics['avg_latency']:.2f}s")


if __name__ == "__main__":
    test_adapter()