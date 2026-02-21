import os
import time
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict, Counter
import jieba
import jieba.analyse

from .storage import get_all_documents, get_document_info
from .classifier import CATEGORY_KEYWORDS, EXTENSION_CATEGORY
from config import EXTENSION_TO_DIR

logger = logging.getLogger(__name__)

MEANINGLESS_PATTERNS = [
    r'^[.\-_~*#=]+$',
    r'^[a-zA-Z]{1,2}$',
    r'^\d+$',
    r'^(the|a|an|is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|could|should|may|might|must|shall|can|need|dare|ought|used|to|of|in|for|on|with|at|by|from|as|into|through|during|before|after|above|below|between|under|again|further|then|once|here|there|when|where|why|how|all|each|few|more|most|other|some|such|no|nor|not|only|own|same|so|than|too|very|just|and|but|if|or|because|as|until|while|content|width|height|rem|html|package|found|home|zyq|root|test|your|name|file|format|cannot|determined)$',
]

CHINESE_STOPWORDS = {
    '的', '了', '和', '是', '在', '对', '与', '等', '这', '那', '有', '个', '也', '就',
    '不', '人', '都', '一', '一个', '上', '很', '到', '说', '要', '去', '你',
    '会', '着', '没有', '看', '好', '自己', '我们', '你们', '他们', '它们',
    '这个', '那个', '什么', '怎么', '如何', '为什么', '因为', '所以'
}

class MultiLevelClassifier:
    """多级分类器：内容分类 → 文件类型 → 时间"""

    def __init__(self):
        self.content_summaries = {}
        self.classification_tree = {}
        self._load_classifier_model()

    def _load_classifier_model(self):
        """加载分类模型"""
        from .classifier import _init_classifier
        _init_classifier()
        logger.info("多级分类器模型已加载")

    def _is_meaningless_keyword(self, keyword: str) -> bool:
        """检查关键词是否无意义"""
        if not keyword or len(keyword.strip()) < 2:
            return True

        keyword = keyword.strip().lower()

        for pattern in MEANINGLESS_PATTERNS:
            if re.match(pattern, keyword, re.IGNORECASE):
                return True

        if keyword in CHINESE_STOPWORDS:
            return True

        if re.match(r'^[a-z]{1,3}$', keyword) and keyword not in ['pdf', 'api', 'url', 'sql', 'cpu', 'gpu', 'ai', 'llm', 'nlp', 'cv']:
            return True

        return False

    def _extract_content_keywords(self, content: str, top_k: int = 10) -> List[str]:
        """从文档内容中提取关键词"""
        try:
            if not content or len(content.strip()) < 50:
                return []

            content = re.sub(r'[.\-_~*#=]{3,}', ' ', content)
            content = re.sub(r'\s+', ' ', content)

            keywords = jieba.analyse.extract_tags(content, topK=top_k * 3, withWeight=False)

            meaningful_keywords = [
                kw for kw in keywords
                if not self._is_meaningless_keyword(kw)
            ][:top_k]

            if not meaningful_keywords:
                keywords = jieba.lcut(content)
                meaningful_keywords = [
                    kw for kw in keywords
                    if len(kw) >= 2 and not self._is_meaningless_keyword(kw)
                ][:top_k]

            return meaningful_keywords if meaningful_keywords else []
        except Exception as e:
            logger.error(f"提取关键词失败: {str(e)}")
            return []

    def _classify_by_filename(self, filename: str) -> tuple:
        """基于文件名进行快速分类"""
        if not filename:
            return None, 0.0

        from .classifier import _classify_by_filename as classifier_by_filename
        return classifier_by_filename(filename)

    def _determine_content_category(self, content: str, filename: str) -> str:
        """确定内容分类（使用classifier中的分类逻辑）"""
        try:
            from .classifier import classify_by_content
            categories, confidence = classify_by_content(content, filename)
            if categories:
                return categories[0]
            return "其他文档"
        except Exception as e:
            logger.error(f"确定内容分类失败: {str(e)}")
            return "其他文档"

    def _get_file_type(self, filename: str) -> str:
        """获取文件类型目录名称"""
        ext = os.path.splitext(filename)[1].lower()
        return EXTENSION_TO_DIR.get(ext, 'other')

    def _get_time_group(self, timestamp: float) -> str:
        """获取时间分组（年月格式）"""
        try:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y年%m月")
        except Exception as e:
            logger.error(f"时间分组失败: {str(e)}")
            return "未知时间"

    def classify_document(self, doc_info: Dict[str, Any], use_llm: bool = False) -> Dict[str, Any]:
        """对单个文档进行多级分类"""
        try:
            filename = doc_info.get('filename', '')
            content = doc_info.get('preview_content', '')

            filename_category, filename_conf = self._classify_by_filename(filename)
            if filename_category and filename_conf > 0.5:
                content_category = filename_category
            else:
                content_category = self._determine_content_category(content, filename)

            content_keywords = self._extract_content_keywords(content)
            file_type = self._get_file_type(filename)
            timestamp = doc_info.get('created_at', time.time())
            time_group = self._get_time_group(timestamp)

            return {
                'document_id': doc_info.get('id'),
                'filename': filename,
                'content_keywords': content_keywords,
                'content_category': content_category,
                'file_type': file_type,
                'time_group': time_group,
                'timestamp': timestamp,
                'created_at_iso': doc_info.get('created_at_iso'),
                'classification_path': f"{content_category}/{file_type}/{time_group}"
            }
        except Exception as e:
            logger.error(f"文档多级分类失败: {str(e)}")
            return None

    def classify_document_with_llm(self, doc_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """使用LLM进行智能分类（可选功能）"""
        try:
            from .llm_classifier import classify_with_llm
            return classify_with_llm(doc_info)
        except ImportError:
            logger.warning("LLM分类器未安装，将使用传统方法")
            return self.classify_document(doc_info, use_llm=False)
        except Exception as e:
            logger.error(f"LLM分类失败: {str(e)}")
            return self.classify_document(doc_info, use_llm=False)

    def build_classification_tree(self, use_llm: bool = False) -> Dict[str, Any]:
        """构建多级分类树"""
        try:
            all_docs = get_all_documents()
            classification_tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

            for doc in all_docs:
                if use_llm:
                    classification = self.classify_document_with_llm(doc)
                else:
                    classification = self.classify_document(doc)

                if classification and classification.get('document_id'):
                    content_cat = classification['content_category']
                    file_type = classification['file_type']
                    time_group = classification['time_group']
                    classification_tree[content_cat][file_type][time_group].append(classification)

            tree_result = {
                'generated_at': datetime.now().isoformat(),
                'total_documents': len(all_docs),
                'tree': self._sort_tree_by_time(self._convert_to_dict(classification_tree)),
                'classification_method': 'llm' if use_llm else 'keyword'
            }

            return tree_result
        except Exception as e:
            logger.error(f"构建分类树失败: {str(e)}")
            return {
                'generated_at': datetime.now().isoformat(),
                'total_documents': 0,
                'tree': {},
                'error': str(e)
            }

    def _sort_tree_by_time(self, tree: Dict) -> Dict:
        """按时间倒序排序"""
        sorted_tree = {}

        for content_cat, types in tree.items():
            sorted_tree[content_cat] = {}
            for file_type, times in types.items():
                sorted_tree[content_cat][file_type] = {}

                sorted_time_groups = sorted(times.items(), key=lambda x: x[0], reverse=True)

                for time_group, docs in sorted_time_groups:
                    sorted_docs = sorted(docs, key=lambda x: x.get('timestamp', 0), reverse=True)
                    sorted_tree[content_cat][file_type][time_group] = sorted_docs

        return sorted_tree

    def _convert_to_dict(self, d):
        """将defaultdict转换为普通dict"""
        if isinstance(d, defaultdict):
            d = {k: self._convert_to_dict(v) for k, v in d.items()}
        return d

    def save_classification_tree(self, tree: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """保存分类树为JSON文件"""
        try:
            if output_path is None:
                from config import DATA_DIR
                output_path = DATA_DIR / "classification_tree.json"

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(tree, f, ensure_ascii=False, indent=2)

            logger.info(f"分类树已保存: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"保存分类树失败: {str(e)}")
            return ""

    def load_classification_tree(self, input_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """加载分类树"""
        try:
            if input_path is None:
                from config import DATA_DIR
                input_path = DATA_DIR / "classification_tree.json"

            input_path = Path(input_path)
            if not input_path.exists():
                return None

            with open(input_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载分类树失败: {str(e)}")
            return None


_multi_level_classifier = None

def get_multi_level_classifier() -> MultiLevelClassifier:
    """获取多级分类器单例"""
    global _multi_level_classifier
    if _multi_level_classifier is None:
        _multi_level_classifier = MultiLevelClassifier()
    return _multi_level_classifier

def build_and_save_classification_tree(use_llm: bool = False) -> Dict[str, Any]:
    """构建并保存分类树的便捷函数"""
    classifier = get_multi_level_classifier()
    tree = classifier.build_classification_tree(use_llm=use_llm)
    classifier.save_classification_tree(tree)
    return tree

def get_classification_tree(use_llm: bool = False) -> Optional[Dict[str, Any]]:
    """获取分类树"""
    classifier = get_multi_level_classifier()

    tree = classifier.load_classification_tree()
    if tree is None:
        tree = build_and_save_classification_tree(use_llm=use_llm)

    current_method = tree.get('classification_method', 'keyword')
    if use_llm and current_method != 'llm':
        tree = build_and_save_classification_tree(use_llm=True)

    return tree
