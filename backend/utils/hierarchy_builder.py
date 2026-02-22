import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from .semantic_segmenter import SemanticSegment, SemanticSegmenter

logger = logging.getLogger(__name__)


@dataclass
class HierarchyNode:
    """层次结构节点"""
    id: str
    level: int
    title: str
    content: str
    summary: str
    children: List['HierarchyNode']
    metadata: Dict

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'id': self.id,
            'level': self.level,
            'title': self.title,
            'content': self.content,
            'summary': self.summary,
            'children': [child.to_dict() for child in self.children],
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HierarchyNode':
        """从字典创建节点"""
        children = [cls.from_dict(child) for child in data.get('children', [])]
        return cls(
            id=data['id'],
            level=data['level'],
            title=data['title'],
            content=data['content'],
            summary=data['summary'],
            children=children,
            metadata=data.get('metadata', {})
        )


class HierarchyBuilder:
    """层次结构构建器 - 构建文档的层次化结构"""

    def __init__(self):
        self.segmenter = SemanticSegmenter()

    def build_hierarchy(self, content: str, doc_id: str) -> HierarchyNode:
        """
        构建文档的层次结构
        
        Args:
            content: 文档内容
            doc_id: 文档ID
            
        Returns:
            根节点
        """
        if not content:
            return HierarchyNode(
                id=f"{doc_id}_root",
                level=0,
                title="Root",
                content="",
                summary="",
                children=[],
                metadata={}
            )
        
        segments = self.segmenter.segment(content)
        
        root = HierarchyNode(
            id=f"{doc_id}_root",
            level=0,
            title="文档根节点",
            content=content[:500] + "..." if len(content) > 500 else content,
            summary=self._generate_summary(content),
            children=[],
            metadata={
                'total_segments': len(segments),
                'created_at': datetime.now().isoformat()
            }
        )
        
        for segment in segments:
            node = self._create_node_from_segment(segment, doc_id)
            self._insert_node(root, node)
        
        logger.info(f"层次结构构建完成: 文档{doc_id}, 共{len(root.children)}个一级节点")
        return root

    def _create_node_from_segment(self, segment: SemanticSegment, doc_id: str) -> HierarchyNode:
        """从语义分段创建节点"""
        node_id = f"{doc_id}_seg_{segment.start_pos}_{segment.end_pos}"
        
        return HierarchyNode(
            id=node_id,
            level=segment.level,
            title=segment.title or f"分段 {segment.start_pos}",
            content=segment.content,
            summary=self._generate_summary(segment.content),
            children=[],
            metadata={
                'start_pos': segment.start_pos,
                'end_pos': segment.end_pos,
                'content_length': len(segment.content)
            }
        )

    def _insert_node(self, parent: HierarchyNode, node: HierarchyNode):
        """将节点插入到层次结构中"""
        if node.level <= parent.level:
            parent.children.append(node)
            return
        
        if not parent.children:
            parent.children.append(node)
            return
        
        last_child = parent.children[-1]
        if node.level > last_child.level:
            self._insert_node(last_child, node)
        else:
            parent.children.append(node)

    def _generate_summary(self, content: str, max_length: int = 200) -> str:
        """生成内容摘要"""
        if not content:
            return ""
        
        sentences = self.segmenter.split_into_sentences(content)
        
        summary_sentences = []
        total_length = 0
        
        for sentence in sentences:
            if total_length + len(sentence) <= max_length:
                summary_sentences.append(sentence)
                total_length += len(sentence)
            else:
                break
        
        summary = ' '.join(summary_sentences)
        
        if len(content) > max_length:
            summary += "..."
        
        return summary

    def flatten_hierarchy(self, root: HierarchyNode, max_depth: int = 3) -> List[Dict]:
        """
        将层次结构扁平化
        
        Args:
            root: 根节点
            max_depth: 最大深度
            
        Returns:
            扁平化的节点列表
        """
        flat_list = []
        
        def traverse(node: HierarchyNode, current_depth: int):
            if current_depth > max_depth:
                return
            
            flat_list.append({
                'id': node.id,
                'level': node.level,
                'title': node.title,
                'summary': node.summary,
                'content_length': len(node.content),
                'depth': current_depth
            })
            
            for child in node.children:
                traverse(child, current_depth + 1)
        
        traverse(root, 0)
        return flat_list

    def get_content_by_level(self, root: HierarchyNode, level: int) -> List[Dict]:
        """
        获取指定层级的所有内容
        
        Args:
            root: 根节点
            level: 目标层级
            
        Returns:
            该层级的节点列表
        """
        result = []
        
        def traverse(node: HierarchyNode):
            if node.level == level:
                result.append({
                    'id': node.id,
                    'title': node.title,
                    'content': node.content,
                    'summary': node.summary
                })
            
            for child in node.children:
                traverse(child)
        
        traverse(root)
        return result

    def build_table_of_contents(self, root: HierarchyNode) -> List[Dict]:
        """
        构建目录结构
        
        Args:
            root: 根节点
            
        Returns:
            目录列表
        """
        toc = []
        
        def traverse(node: HierarchyNode, parent_path: str = ""):
            current_path = f"{parent_path} > {node.title}" if parent_path else node.title
            
            if node.level > 0:
                toc.append({
                    'level': node.level,
                    'title': node.title,
                    'path': current_path,
                    'node_id': node.id
                })
            
            for child in node.children:
                traverse(child, current_path)
        
        traverse(root)
        return toc

    def optimize_hierarchy(self, root: HierarchyNode, min_content_length: int = 50) -> HierarchyNode:
        """
        优化层次结构
        
        Args:
            root: 根节点
            min_content_length: 最小内容长度
            
        Returns:
            优化后的根节点
        """
        def optimize_node(node: HierarchyNode) -> Optional[HierarchyNode]:
            if len(node.content) < min_content_length and node.children:
                if len(node.children) == 1:
                    return optimize_node(node.children[0])
                else:
                    node.content = ""
            
            optimized_children = []
            for child in node.children:
                optimized_child = optimize_node(child)
                if optimized_child:
                    optimized_children.append(optimized_child)
            
            node.children = optimized_children
            return node
        
        return optimize_node(root)

    def export_hierarchy(self, root: HierarchyNode, format: str = 'dict') -> Dict:
        """
        导出层次结构
        
        Args:
            root: 根节点
            format: 导出格式 ('dict', 'flat', 'toc')
            
        Returns:
            导出的数据
        """
        if format == 'dict':
            return root.to_dict()
        elif format == 'flat':
            return self.flatten_hierarchy(root)
        elif format == 'toc':
            return self.build_table_of_contents(root)
        else:
            return root.to_dict()