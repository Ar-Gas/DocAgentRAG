"""
LLM智能分类器 - 使用大模型进行文档分类
支持 OpenAI 兼容 API（如 DeepSeek, GLM, Qwen 等）
"""
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_llm_client = None

# 分类类别描述
CATEGORY_DESCRIPTIONS = """
分类体系包含以下类别：

# 学术论文类
- 学术论文-计算机：计算机科学、人工智能、机器学习、深度学习、算法等
- 学术论文-数学：数学研究、概率论、数理统计等
- 学术论文-物理：物理学研究、量子力学等
- 学术论文-化学：化学研究、有机化学等
- 学术论文-生物：生物学研究、基因工程等
- 学术论文-医学：医学研究、临床医学等
- 学术论文-经济管理：经济学、管理学研究
- 学术论文-教育：教育学研究
- 学术论文-法学：法学研究
- 学术论文-其他：其他学术论文

# 办公文档类
- 办公-合同协议：合同、协议
- 办公-报告总结：报告、总结
- 办公-通知公告：通知、公告
- 办公-简历求职：简历、求职信
- 办公-规章制度：制度、规定
- 办公-申请表：申请表、报名表
- 办公-PPT演示：PPT、演示文稿
- 办公-邮件：邮件

# 技术文档类
- 技术文档-编程开发：代码、程序、开发文档
- 技术文档-架构设计：架构、设计模式
- 技术文档-操作手册：手册、指南
- 技术文档-产品需求：需求文档
- 技术文档-测试文档：测试用例
- 技术文档-数据库：数据库文档

# 书籍资料类
- 书籍-编程技术：编程技术书籍
- 书籍-操作系统：操作系统书籍
- 书籍-网络通信：网络通信书籍
- 书籍-数据库技术：数据库书籍
- 书籍-人工智能：AI书籍
- 书籍-数学基础：数学教材
- 书籍-经济管理：经管书籍
- 书籍-教材-高等教育：大学教材
- 书籍-教材-中小学：中小学教材
- 书籍-其他出版物：其他书籍

# 数据文档类
- 数据文档-Excel表格：Excel文件
- 数据文档-CSV数据：CSV文件
- 数据文档-数据库导出：数据库导出文件

# 财务文档类
- 财务-财务报表
- 财务-预算决算
- 财务-发票凭证
- 财务-税务

# 法律文档类
- 法律-法律法规
- 法律-诉讼文书
- 法律-公证

# 会议文档类
- 会议-会议纪要
- 会议-议程安排
- 会议-签到表

# 项目文档类
- 项目-项目计划
- 项目-项目总结
- 项目-任务分配

# 人力资源类
- 人力-招聘培训
- 人力-绩效薪酬
- 人力-员工档案

# 营销销售类
- 营销-策划方案
- 营销-市场分析
- 营销-销售

# 教育培训类
- 教育-教案
- 教育-课件
- 教育-试卷习题

# 产品文档类
- 产品-产品介绍
- 产品-用户手册

# 其他类
- 其他文档
"""


def _get_llm_client():
    """获取LLM客户端"""
    global _llm_client
    if _llm_client is not None:
        return _llm_client

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai库未安装")
        return None

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com")

    if not api_key:
        logger.warning("未配置 OPENAI_API_KEY 环境变量")
        return None

    try:
        _llm_client = OpenAI(api_key=api_key, base_url=base_url)
        logger.info(f"LLM客户端初始化成功: {base_url}")
        return _llm_client
    except Exception as e:
        logger.error(f"LLM客户端初始化失败: {str(e)}")
        return None


def classify_with_llm(doc_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    使用LLM对文档进行智能分类
    :param doc_info: 文档信息
    :return: 分类结果
    """
    client = _get_llm_client()
    if client is None:
        logger.warning("LLM客户端不可用，使用传统分类方法")
        return None

    filename = doc_info.get('filename', '')
    content = doc_info.get('preview_content', '')

    preview = content[:2000] if content else ''

    prompt = f"""你是一个专业的文档分类助手。请根据文件名和文档内容，为文档分类。

文件名: {filename}
文档内容预览:
{preview}

{CATEGORY_DESCRIPTIONS}

请从上述分类体系中选择最合适的一个分类，只返回分类名称，不要其他内容。
例如：书籍-编程技术

分类结果："""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.1
        )

        category = response.choices[0].message.content.strip()
        logger.info(f"LLM分类结果: {filename} -> {category}")

        import time
        from datetime import datetime

        return {
            'document_id': doc_info.get('id'),
            'filename': filename,
            'content_keywords': [],
            'content_category': category,
            'file_type': doc_info.get('file_type', 'pdf').replace('.', ''),
            'time_group': datetime.fromtimestamp(
                doc_info.get('created_at', time.time())
            ).strftime("%Y年%m月"),
            'timestamp': doc_info.get('created_at', time.time()),
            'created_at_iso': doc_info.get('created_at_iso'),
            'classification_path': f"{category}/{doc_info.get('file_type', 'pdf').replace('.', '')}/{datetime.fromtimestamp(doc_info.get('created_at', time.time())).strftime('%Y年%m月')}",
            'classification_method': 'llm'
        }
    except Exception as e:
        logger.error(f"LLM分类失败: {str(e)}")
        return None


def is_llm_available() -> bool:
    """检查LLM是否可用"""
    return _get_llm_client() is not None
