import re
import logging
from typing import List, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SemanticSegment:
    """语义分段数据结构"""
    content: str
    level: int
    title: str
    start_pos: int
    end_pos: int
    metadata: Dict


class SemanticSegmenter:
    """语义分段器 - 按语义层次划分内容"""

    def __init__(self):
        self.title_patterns = self._init_title_patterns()
        self.sentence_separators = ['。', '！', '？', '. ', '! ', '? ', '; ', '；']

    def _init_title_patterns(self) -> List[Tuple[int, str]]:
        """初始化标题模式 (level, pattern)"""
        return [
            (1, r'^第[一二三四五六七八九十\d]+章\s+.*$'),
            (1, r'^Chapter\s+\d+.*$', re.IGNORECASE),
            (1, r'^第[一二三四五六七八九十\d]+篇\s+.*$'),
            (2, r'^第[一二三四五六七八九十\d]+节\s+.*$'),
            (2, r'^Section\s+\d+.*$', re.IGNORECASE),
            (2, r'^\d+\.\s+.*$'),
            (2, r'^\d+\.\d+\s+.*$'),
            (3, r'^\d+\.\d+\.\d+\s+.*$'),
            (3, r'^[一二三四五六七八九十]+、\s+.*$'),
            (3, r'^[A-Z][a-z]+\s+.*$'),
            (4, r'^\([一二三四五六七八九十\d]+\)\s+.*$'),
            (4, r'^[a-z]\)\s+.*$'),
        ]

    def segment(self, content: str) -> List[SemanticSegment]:
        """
        对内容进行语义分段
        
        Args:
            content: 文档内容
            
        Returns:
            语义分段列表
        """
        if not content:
            return []
        
        segments = []
        lines = content.split('\n')
        current_segment = []
        current_level = 0
        current_title = ""
        start_pos = 0
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            title_info = self._identify_title(line)
            
            if title_info:
                if current_segment:
                    segment_content = '\n'.join(current_segment).strip()
                    if segment_content:
                        segments.append(SemanticSegment(
                            content=segment_content,
                            level=current_level,
                            title=current_title,
                            start_pos=start_pos,
                            end_pos=i,
                            metadata={}
                        ))
                
                current_segment = []
                current_level = title_info['level']
                current_title = title_info['title']
                start_pos = i
                current_segment.append(line)
            else:
                current_segment.append(line)
        
        if current_segment:
            segment_content = '\n'.join(current_segment).strip()
            if segment_content:
                segments.append(SemanticSegment(
                    content=segment_content,
                    level=current_level,
                    title=current_title,
                    start_pos=start_pos,
                    end_pos=len(lines),
                    metadata={}
                ))
        
        logger.info(f"语义分段完成: 共{len(segments)}个分段")
        return segments

    def _identify_title(self, line: str) -> Dict:
        """
        识别标题
        
        Args:
            line: 文本行
            
        Returns:
            标题信息字典 {'level': int, 'title': str} 或 None
        """
        for pattern_info in self.title_patterns:
            if len(pattern_info) == 2:
                level, pattern = pattern_info
                flags = 0
            else:
                level, pattern, flags = pattern_info
            
            if re.match(pattern, line.strip(), flags):
                return {
                    'level': level,
                    'title': line.strip()
                }
        return None

    def split_into_sentences(self, content: str) -> List[str]:
        """
        将内容分割为句子
        
        Args:
            content: 文本内容
            
        Returns:
            句子列表
        """
        if not content:
            return []
        
        sentences = []
        current_sentence = ""
        
        for char in content:
            current_sentence += char
            if char in ['。', '！', '？', '.', '!', '?']:
                if current_sentence.strip():
                    sentences.append(current_sentence.strip())
                current_sentence = ""
        
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        return sentences

    def group_sentences_by_meaning(self, sentences: List[str], max_group_size: int = 5) -> List[str]:
        """
        按语义将句子分组
        
        Args:
            sentences: 句子列表
            max_group_size: 每组最大句子数
            
        Returns:
            分组后的文本列表
        """
        if not sentences:
            return []
        
        groups = []
        current_group = []
        
        for sentence in sentences:
            current_group.append(sentence)
            
            if len(current_group) >= max_group_size:
                groups.append(' '.join(current_group))
                current_group = []
        
        if current_group:
            groups.append(' '.join(current_group))
        
        return groups

    def extract_key_points(self, content: str, max_points: int = 10) -> List[str]:
        """
        提取关键点
        
        Args:
            content: 文本内容
            max_points: 最大提取点数
            
        Returns:
            关键点列表
        """
        sentences = self.split_into_sentences(content)
        
        key_points = []
        for sentence in sentences:
            if self._is_key_point(sentence):
                key_points.append(sentence)
                if len(key_points) >= max_points:
                    break
        
        return key_points

    def _is_key_point(self, sentence: str) -> bool:
        """判断句子是否为关键点"""
        if len(sentence) < 10:
            return False
        
        key_indicators = [
            '因此', '所以', '总之', '结论', '核心', '关键',
            '主要', '重要', '必须', '应该', '需要',
            'therefore', 'thus', 'conclusion', 'key', 'important'
        ]
        
        for indicator in key_indicators:
            if indicator in sentence:
                return True
        
        return False

    def build_semantic_tree(self, segments: List[SemanticSegment]) -> Dict:
        """
        构建语义树结构
        
        Args:
            segments: 语义分段列表
            
        Returns:
            语义树字典
        """
        tree = {
            'level': 0,
            'title': 'Root',
            'content': '',
            'children': []
        }
        
        stack = [tree]
        
        for segment in segments:
            node = {
                'level': segment.level,
                'title': segment.title,
                'content': segment.content,
                'children': []
            }
            
            while stack and stack[-1]['level'] >= segment.level:
                stack.pop()
            
            if stack:
                stack[-1]['children'].append(node)
                stack.append(node)
        
        return tree

    def optimize_segmentation(self, content: str, target_chunk_size: int = 500) -> List[str]:
        """
        优化的分段方法，结合语义和长度
        
        Args:
            content: 文本内容
            target_chunk_size: 目标分段大小
            
        Returns:
            优化后的分段列表
        """
        segments = self.segment(content)
        optimized_chunks = []
        
        for segment in segments:
            if len(segment.content) <= target_chunk_size:
                optimized_chunks.append(segment.content)
            else:
                sentences = self.split_into_sentences(segment.content)
                current_chunk = ""
                
                for sentence in sentences:
                    if len(current_chunk + sentence) <= target_chunk_size:
                        current_chunk += sentence + " "
                    else:
                        if current_chunk.strip():
                            optimized_chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "
                
                if current_chunk.strip():
                    optimized_chunks.append(current_chunk.strip())
        
        logger.info(f"优化分段完成: 共{len(optimized_chunks)}个分段")
        return optimized_chunks