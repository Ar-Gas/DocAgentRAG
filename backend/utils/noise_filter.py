import re
import logging
from typing import List, Dict, Tuple
from collections import Counter

logger = logging.getLogger(__name__)


class NoiseFilter:
    """文档噪音过滤器"""

    def __init__(self):
        self.patterns = self._init_patterns()

    def _init_patterns(self) -> Dict[str, List[str]]:
        """初始化噪音模式"""
        return {
            'page_header': [
                r'^第\s*\d+\s*页$',
                r'^Page\s*\d+\s*of\s*\d+$',
                r'^\d+\s*/\s*\d+$',
            ],
            'page_footer': [
                r'^-+\s*\d+\s*-+$',
                r'^保密.*$',
                r'^机密.*$',
                r'^Confidential.*$',
            ],
            'empty_lines': [
                r'^\s*$',
            ],
            'repeated_chars': [
                r'(.)\1{10,}',
            ],
            'ocr_noise': [
                r'^[^\w\u4e00-\u9fa5\s]{20,}$',
                r'^\s*[|=_\-]{20,}\s*$',
            ],
            'email_noise': [
                r'^From:.*$',
                r'^To:.*$',
                r'^Subject:.*$',
                r'^Date:.*$',
                r'^Message-ID:.*$',
            ]
        }

    def filter_content(self, content: str) -> Tuple[str, Dict]:
        """
        过滤文档内容中的噪音
        
        Args:
            content: 原始文档内容
            
        Returns:
            (过滤后的内容, 过滤统计信息)
        """
        if not content:
            return content, {}
        
        lines = content.split('\n')
        filtered_lines = []
        stats = {
            'total_lines': len(lines),
            'removed_lines': 0,
            'removed_by_type': {}
        }
        
        for line in lines:
            if self._is_noise_line(line):
                noise_type = self._identify_noise_type(line)
                stats['removed_lines'] += 1
                stats['removed_by_type'][noise_type] = stats['removed_by_type'].get(noise_type, 0) + 1
            else:
                filtered_lines.append(line)
        
        filtered_content = '\n'.join(filtered_lines)
        
        logger.info(f"噪音过滤完成: 移除{stats['removed_lines']}/{stats['total_lines']}行")
        return filtered_content, stats

    def _is_noise_line(self, line: str) -> bool:
        """判断一行是否为噪音"""
        if not line or not line.strip():
            return True
        
        for category, patterns in self.patterns.items():
            for pattern in patterns:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    return True
        
        return False

    def _identify_noise_type(self, line: str) -> str:
        """识别噪音类型"""
        if not line or not line.strip():
            return 'empty_lines'
        
        for category, patterns in self.patterns.items():
            for pattern in patterns:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    return category
        
        return 'unknown'

    def remove_repeated_paragraphs(self, content: str, min_length: int = 20) -> Tuple[str, int]:
        """
        移除重复段落
        
        Args:
            content: 文档内容
            min_length: 最小段落长度（低于此长度不进行重复检测）
            
        Returns:
            (去重后的内容, 移除的重复段落数)
        """
        paragraphs = content.split('\n\n')
        unique_paragraphs = []
        seen_hashes = set()
        removed_count = 0
        
        for para in paragraphs:
            if len(para.strip()) < min_length:
                unique_paragraphs.append(para)
                continue
            
            para_hash = hash(para.strip())
            if para_hash in seen_hashes:
                removed_count += 1
                continue
            
            seen_hashes.add(para_hash)
            unique_paragraphs.append(para)
        
        result = '\n\n'.join(unique_paragraphs)
        logger.info(f"重复段落移除完成: 移除{removed_count}个重复段落")
        return result, removed_count

    def normalize_whitespace(self, content: str) -> str:
        """规范化空白字符"""
        content = re.sub(r'[ \t]+', ' ', content)
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

    def clean_special_chars(self, content: str) -> str:
        """清理特殊字符"""
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', content)
        content = re.sub(r'\u3000+', ' ', content)
        return content

    def full_clean(self, content: str) -> Tuple[str, Dict]:
        """
        完整的清理流程
        
        Args:
            content: 原始内容
            
        Returns:
            (清理后的内容, 清理统计信息)
        """
        stats = {
            'original_length': len(content),
            'steps': []
        }
        
        # 步骤1: 清理特殊字符
        content = self.clean_special_chars(content)
        stats['steps'].append('clean_special_chars')
        
        # 步骤2: 过滤噪音行
        content, filter_stats = self.filter_content(content)
        stats['steps'].append('filter_content')
        stats['filter_stats'] = filter_stats
        
        # 步骤3: 移除重复段落
        content, removed_count = self.remove_repeated_paragraphs(content)
        stats['steps'].append('remove_repeated_paragraphs')
        stats['removed_paragraphs'] = removed_count
        
        # 步骤4: 规范化空白字符
        content = self.normalize_whitespace(content)
        stats['steps'].append('normalize_whitespace')
        
        stats['final_length'] = len(content)
        stats['reduction_ratio'] = (1 - stats['final_length'] / stats['original_length']) * 100
        
        logger.info(f"完整清理完成: 长度从{stats['original_length']}减少到{stats['final_length']}, 减少{stats['reduction_ratio']:.2f}%")
        return content, stats