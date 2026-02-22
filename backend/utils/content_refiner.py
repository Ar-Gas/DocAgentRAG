import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from .noise_filter import NoiseFilter
from .semantic_segmenter import SemanticSegmenter, SemanticSegment
from .hierarchy_builder import HierarchyBuilder, HierarchyNode

logger = logging.getLogger(__name__)


@dataclass
class RefinementResult:
    """内容提炼结果"""
    original_content: str
    refined_content: str
    hierarchy: Dict
    statistics: Dict
    metadata: Dict

    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)


class ContentRefiner:
    """内容提炼引擎 - 整合去噪、分段、层次化"""

    def __init__(self):
        self.noise_filter = NoiseFilter()
        self.semantic_segmenter = SemanticSegmenter()
        self.hierarchy_builder = HierarchyBuilder()

    def refine_document(self, content: str, doc_id: str, options: Optional[Dict] = None) -> RefinementResult:
        """
        完整的文档提炼流程
        
        Args:
            content: 原始文档内容
            doc_id: 文档ID
            options: 提炼选项
            
        Returns:
            提炼结果
        """
        if not content:
            return RefinementResult(
                original_content="",
                refined_content="",
                hierarchy={},
                statistics={},
                metadata={}
            )
        
        options = options or {}
        start_time = datetime.now()
        
        logger.info(f"开始提炼文档: {doc_id}, 原始长度: {len(content)}")
        
        # 步骤1: 噪音过滤
        cleaned_content, noise_stats = self.noise_filter.full_clean(content)
        
        # 步骤2: 语义分段
        segments = self.semantic_segmenter.segment(cleaned_content)
        
        # 步骤3: 构建层次结构
        hierarchy_root = self.hierarchy_builder.build_hierarchy(cleaned_content, doc_id)
        hierarchy_root = self.hierarchy_builder.optimize_hierarchy(hierarchy_root)
        
        # 步骤4: 生成优化后的内容
        refined_content = self._generate_refined_content(hierarchy_root)
        
        # 步骤5: 生成统计信息
        statistics = self._generate_statistics(
            original_content=content,
            refined_content=refined_content,
            noise_stats=noise_stats,
            segments=segments,
            hierarchy_root=hierarchy_root
        )
        
        # 步骤6: 生成元数据
        metadata = {
            'doc_id': doc_id,
            'refined_at': datetime.now().isoformat(),
            'processing_time': (datetime.now() - start_time).total_seconds(),
            'options': options
        }
        
        result = RefinementResult(
            original_content=content,
            refined_content=refined_content,
            hierarchy=hierarchy_root.to_dict(),
            statistics=statistics,
            metadata=metadata
        )
        
        logger.info(f"文档提炼完成: {doc_id}, 优化后长度: {len(refined_content)}, 耗时: {metadata['processing_time']:.2f}秒")
        return result

    def _generate_refined_content(self, hierarchy_root: HierarchyNode) -> str:
        """生成优化后的内容"""
        refined_parts = []
        
        def traverse(node: HierarchyNode, depth: int = 0):
            if node.level > 0:
                prefix = "#" * node.level + " "
                refined_parts.append(f"{prefix}{node.title}")
                
                if node.summary:
                    refined_parts.append(f"\n{node.summary}\n")
                else:
                    refined_parts.append("")
            
            for child in node.children:
                traverse(child, depth + 1)
        
        traverse(hierarchy_root)
        return '\n'.join(refined_parts)

    def _generate_statistics(self, original_content: str, refined_content: str,
                            noise_stats: Dict, segments: List[SemanticSegment],
                            hierarchy_root: HierarchyNode) -> Dict:
        """生成统计信息"""
        def count_nodes(node: HierarchyNode) -> int:
            return 1 + sum(count_nodes(child) for child in node.children)
        
        return {
            'original_length': len(original_content),
            'refined_length': len(refined_content),
            'reduction_ratio': (1 - len(refined_content) / len(original_content)) * 100 if original_content else 0,
            'noise_filter_stats': noise_stats,
            'segment_count': len(segments),
            'hierarchy_node_count': count_nodes(hierarchy_root),
            'hierarchy_depth': self._calculate_max_depth(hierarchy_root),
            'avg_segment_length': sum(len(s.content) for s in segments) / len(segments) if segments else 0
        }

    def _calculate_max_depth(self, node: HierarchyNode) -> int:
        """计算层次结构的最大深度"""
        if not node.children:
            return node.level
        return max(self._calculate_max_depth(child) for child in node.children)

    def refine_for_retrieval(self, content: str, doc_id: str, 
                           chunk_size: int = 500, overlap: int = 50) -> List[Dict]:
        """
        为检索优化的提炼方法
        
        Args:
            content: 原始内容
            doc_id: 文档ID
            chunk_size: 分块大小
            overlap: 重叠大小
            
        Returns:
            优化后的分块列表
        """
        if not content:
            return []
        
        cleaned_content, _ = self.noise_filter.full_clean(content)
        optimized_chunks = self.semantic_segmenter.optimize_segmentation(cleaned_content, chunk_size)
        
        chunks = []
        for i, chunk in enumerate(optimized_chunks):
            chunks.append({
                'id': f"{doc_id}_chunk_{i}",
                'content': chunk,
                'chunk_index': i,
                'chunk_length': len(chunk),
                'metadata': {
                    'doc_id': doc_id,
                    'refined': True
                }
            })
        
        logger.info(f"检索优化提炼完成: {doc_id}, 共{len(chunks)}个分块")
        return chunks

    def extract_key_information(self, content: str) -> Dict:
        """
        提取关键信息
        
        Args:
            content: 文档内容
            
        Returns:
            关键信息字典
        """
        if not content:
            return {}
        
        cleaned_content, _ = self.noise_filter.full_clean(content)
        
        key_points = self.semantic_segmenter.extract_key_points(cleaned_content)
        segments = self.semantic_segmenter.segment(cleaned_content)
        
        return {
            'key_points': key_points,
            'main_topics': [s.title for s in segments if s.title and s.level <= 2],
            'summary': self._generate_document_summary(cleaned_content),
            'structure': {
                'total_segments': len(segments),
                'max_level': max(s.level for s in segments) if segments else 0
            }
        }

    def _generate_document_summary(self, content: str, max_sentences: int = 5) -> str:
        """生成文档摘要"""
        sentences = self.semantic_segmenter.split_into_sentences(content)
        
        summary_sentences = sentences[:max_sentences]
        summary = ' '.join(summary_sentences)
        
        if len(content) > len(summary):
            summary += "..."
        
        return summary

    def compare_content(self, original: str, refined: str) -> Dict:
        """
        比较原始内容和提炼后内容
        
        Args:
            original: 原始内容
            refined: 提炼后内容
            
        Returns:
            比较结果
        """
        original_sentences = self.semantic_segmenter.split_into_sentences(original)
        refined_sentences = self.semantic_segmenter.split_into_sentences(refined)
        
        return {
            'original': {
                'length': len(original),
                'sentence_count': len(original_sentences),
                'avg_sentence_length': sum(len(s) for s in original_sentences) / len(original_sentences) if original_sentences else 0
            },
            'refined': {
                'length': len(refined),
                'sentence_count': len(refined_sentences),
                'avg_sentence_length': sum(len(s) for s in refined_sentences) / len(refined_sentences) if refined_sentences else 0
            },
            'improvement': {
                'length_reduction': (1 - len(refined) / len(original)) * 100 if original else 0,
                'sentence_reduction': (1 - len(refined_sentences) / len(original_sentences)) * 100 if original_sentences else 0,
                'conciseness_ratio': len(refined) / len(original) if original else 0
            }
        }

    def save_refinement_result(self, result: RefinementResult, output_path: str) -> bool:
        """
        保存提炼结果到文件
        
        Args:
            result: 提炼结果
            output_path: 输出路径
            
        Returns:
            是否成功
        """
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                import json
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            
            logger.info(f"提炼结果已保存: {output_path}")
            return True
        except Exception as e:
            logger.error(f"保存提炼结果失败: {str(e)}")
            return False

    def load_refinement_result(self, input_path: str) -> Optional[RefinementResult]:
        """
        从文件加载提炼结果
        
        Args:
            input_path: 输入路径
            
        Returns:
            提炼结果或None
        """
        try:
            import json
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            result = RefinementResult(**data)
            logger.info(f"提炼结果已加载: {input_path}")
            return result
        except Exception as e:
            logger.error(f"加载提炼结果失败: {str(e)}")
            return None