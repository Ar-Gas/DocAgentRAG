import os
import time
import re
import shutil
import jieba
import logging
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from pathlib import Path
from .retriever import search_documents  # 修正导入

# ===================== 规范：配置日志 =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===================== 配置：分类与目录 =====================
# 预定义文档类别及其关键词（优化：增加更精准的关键词）
CATEGORY_KEYWORDS = {
    '报告文档': ['报告', '分析', '总结', '评估', '调研', '研究', '考察', '检测', '鉴定', '白皮书', '年报'],
    '法律文档': ['合同', '协议', '条款', '法规', '法律', '诉讼', '仲裁', '调解', '判决', '律师函', '承诺书'],
    '邮件文档': ['邮件', 'email', '发件人', '收件人', '抄送', '主题', '回复', '转发', 'eml', 'msg'],
    '数据文档': ['表格', '数据', '统计', 'excel', 'csv', '数据库', '报表', '图表', '分析', 'xlsx', 'xls'],
    '会议文档': ['会议', '纪要', '讨论', '议程', '议题', '决议', '参会', '记录', '汇报', '日程'],
    '技术文档': ['技术', '代码', '架构', '设计', '开发', '测试', '部署', '运维', '文档', 'api', '接口'],
    '财务文档': ['财务', '报表', '预算', '报销', '会计', '审计', '税务', '成本', '收入', '发票', '账单'],
    '人力资源文档': ['招聘', '培训', '员工', '人事', '绩效', '考核', '福利', '薪酬', '离职', 'offer', '劳动合同']
}

# 扩展名辅助分类（快速路径）
EXTENSION_CATEGORY = {
    '.eml': '邮件文档',
    '.msg': '邮件文档',
    '.xlsx': '数据文档',
    '.xls': '数据文档',
    '.csv': '数据文档'
}

# 全局变量（懒加载）
_vectorizer = None
_category_vectors = None
_category_names = None

# ===================== 工具：中文分词 =====================
def _chinese_tokenizer(text):
    """自定义中文分词器，用于TF-IDF"""
    return jieba.lcut(text)

# ===================== 工具：懒加载分类模型 =====================
def _init_classifier():
    """懒加载TF-IDF向量化器和类别特征，避免启动时初始化"""
    global _vectorizer, _category_vectors, _category_names
    if _vectorizer is not None and _category_vectors is not None:
        return
    
    logger.info("初始化文档分类模型...")
    # 1. 为每个类别创建特征文本（关键词+类别名）
    category_texts = []
    _category_names = list(CATEGORY_KEYWORDS.keys())
    for category, keywords in CATEGORY_KEYWORDS.items():
        # 特征文本：类别名 + 关键词重复3次（增加权重）
        feature_text = f"{category} {' '.join(keywords * 3)}"
        category_texts.append(feature_text)
    
    # 2. 创建TF-IDF向量化器（优化：用中文分词）
    _vectorizer = TfidfVectorizer(
        tokenizer=_chinese_tokenizer,
        stop_words=['的', '了', '和', '是', '在', '对', '与', '等'],
        ngram_range=(1, 2)  # 词级1-2gram，更适合中文
    )
    
    # 3. 拟合类别特征
    _category_vectors = _vectorizer.fit_transform(category_texts)
    logger.info("文档分类模型初始化完成")

# ===================== 核心：传统方法分类（修正函数名）=====================
def classify_by_content(content, filename=""):
    """
    基于内容和文件名的文档分类（不用LLM，避免误导）
    :param content: 文档内容
    :param filename: 文件名（可选，用于辅助分类）
    :return: (categories: list, confidence: float)
    """
    try:
        _init_classifier()
        
        # 1. 快速路径：先看扩展名
        ext = os.path.splitext(filename)[1].lower()
        if ext in EXTENSION_CATEGORY:
            logger.info(f"通过扩展名快速分类：{filename} -> {EXTENSION_CATEGORY[ext]}")
            return [EXTENSION_CATEGORY[ext]], 0.9
        
        # 2. 预处理内容
        content = re.sub(r'\s+', ' ', content)
        content = content.lower()
        # 结合文件名
        combined_text = f"{filename} {content}"
        
        # 3. 向量化
        content_vector = _vectorizer.transform([combined_text])
        
        # 4. 计算相似度
        similarities = cosine_similarity(content_vector, _category_vectors)[0]
        
        # 5. 排序并筛选
        category_scores = list(zip(_category_names, similarities))
        category_scores.sort(key=lambda x: x[1], reverse=True)
        
        # 优化：动态阈值（取前3个且相似度>0.2）
        threshold = 0.2
        categories = [cat for cat, score in category_scores if score > threshold][:3]
        confidence = category_scores[0][1] if categories else 0.0
        
        # 兜底
        if not categories:
            categories = ['其他文档']
            confidence = 0.5
        
        return categories, round(confidence, 2)
    except Exception as e:
        logger.error(f"内容分类失败: {str(e)}")
        return ['其他文档'], 0.5

# ===================== 核心：自动创建分类目录并移动文件 =====================
def create_classification_directory(doc_info, categories, base_dir=None):
    """
    自动创建分类目录并移动文件
    :param doc_info: 文档信息（包含id, filename, path）
    :param categories: 分类结果列表
    :param base_dir: 分类目录的根目录（默认在项目根目录下的classified_docs）
    :return: (success: bool, target_path: str)
    """
    try:
        if not categories or not doc_info.get('path'):
            return False, ""
        
        # 1. 设置根目录
        if base_dir is None:
            base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "classified_docs"
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. 取第一个分类创建目录
        primary_category = categories[0]
        category_dir = base_dir / primary_category
        category_dir.mkdir(parents=True, exist_ok=True)
        
        # 3. 移动文件（避免重名）
        original_path = Path(doc_info['path'])
        if not original_path.exists():
            logger.warning(f"原文件不存在，跳过移动：{original_path}")
            return False, ""
        
        # 处理重名：如果目标文件已存在，加后缀
        target_path = category_dir / original_path.name
        counter = 1
        while target_path.exists():
            stem = original_path.stem
            suffix = original_path.suffix
            target_path = category_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        
        # 移动文件
        shutil.move(str(original_path), str(target_path))
        logger.info(f"文件已移动到分类目录：{original_path.name} -> {target_path}")
        
        return True, str(target_path)
    except Exception as e:
        logger.error(f"创建分类目录/移动文件失败: {str(e)}")
        return False, ""

# ===================== 完整：文档分类流水线 =====================
def classify_document(doc_info, auto_move=True, base_dir=None):
    """
    完整的文档分类流水线
    :param doc_info: 文档信息（包含id, filename, path, content）
    :param auto_move: 是否自动创建目录并移动文件
    :param base_dir: 分类目录根目录
    :return: 分类结果字典
    """
    try:
        # 1. 提取信息
        content = doc_info.get('content', '')
        filename = doc_info.get('filename', '')
        filepath = doc_info.get('path', '')
        
        if not content and not filename:
            logger.error("文档信息缺失，无法分类")
            return {
                "document_id": doc_info.get('id', ''),
                "original_filename": filename,
                "classification_result": {
                    "categories": ['其他文档'],
                    "confidence": 0.5,
                    "error": "文档信息缺失"
                },
                "processing_details": {"error": "文档信息缺失"},
                "recommended_actions": ["检查文档信息"]
            }
        
        logger.info(f"开始分类文档：{filename}")
        
        # 2. 分类
        categories, confidence = classify_by_content(content, filename)
        
        # 3. 自动创建目录并移动文件（可选）
        moved = False
        target_path = ""
        if auto_move and categories[0] != '其他文档':
            moved, target_path = create_classification_directory(doc_info, categories, base_dir)
        
        # 4. 生成结果
        classification_result = {
            "categories": categories,
            "confidence": confidence,
            "classification_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "details": {
                "filename_analysis": f"基于文件名 '{filename}' 的分析",
                "content_analysis": "基于文档内容的TF-IDF+余弦相似度分类",
                "extension_quick_match": filepath.split('.')[-1].lower() in EXTENSION_CATEGORY
            },
            "suggested_folders": [f"{cat}/{filename}" for cat in categories],
            "actual_path": target_path if moved else ""
        }
        
        final_result = {
            "document_id": doc_info.get('id', ''),
            "original_filename": filename,
            "original_path": filepath,
            "classification_result": classification_result,
            "processing_details": {
                "content_length": len(content),
                "auto_moved": moved,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            },
            "recommended_actions": [
                "查看分类结果是否准确",
                "如不准确可手动调整分类",
                "基于分类结果设置访问权限"
            ] if not moved else [
                "分类完成，文件已移动到对应目录"
            ]
        }
        
        logger.info(f"文档分类完成：{filename} -> {categories[0]} (置信度: {confidence})")
        return final_result
    except Exception as e:
        logger.error(f"文档分类失败: {str(e)}")
        return {
            "document_id": doc_info.get('id', ''),
            "original_filename": doc_info.get('filename', ''),
            "classification_result": {
                "categories": ['其他文档'],
                "confidence": 0.5,
                "error": str(e)
            },
            "processing_details": {"error": str(e)},
            "recommended_actions": ["检查文档格式", "重新尝试分类"]
        }