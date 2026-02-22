import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.content_refiner import ContentRefiner
from utils.noise_filter import NoiseFilter
from utils.semantic_segmenter import SemanticSegmenter
from utils.hierarchy_builder import HierarchyBuilder, HierarchyNode
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_noise_filter():
    """测试噪音过滤器"""
    print("\n" + "="*80)
    print("测试噪音过滤器")
    print("="*80)
    
    noise_filter = NoiseFilter()
    
    # 测试1: 空内容
    content, stats = noise_filter.filter_content("")
    assert content == "", "空内容测试失败"
    print("✓ 空内容测试通过")
    
    # 测试2: 页眉页脚过滤
    content = "第1页\n正文内容\nPage 2 of 10\n更多内容\n机密文档"
    cleaned, stats = noise_filter.filter_content(content)
    assert "第1页" not in cleaned, "页码过滤失败"
    assert "机密文档" not in cleaned, "机密标识过滤失败"
    assert "正文内容" in cleaned, "正文内容被误删"
    print("✓ 页眉页脚过滤测试通过")
    
    # 测试3: 空白行清理
    content = "段落1\n\n\n\n段落2"
    cleaned = noise_filter.normalize_whitespace(content)
    assert cleaned.count('\n\n') == 1, "空白行规范化失败"
    print("✓ 空白行清理测试通过")
    
    # 测试4: 特殊字符清理
    content = "正常内容\x00\x01特殊字符\u3000\u3000全角空格"
    cleaned = noise_filter.clean_special_chars(content)
    assert '\x00' not in cleaned, "特殊字符清理失败"
    assert '\u3000' not in cleaned, "全角空格清理失败"
    print("✓ 特殊字符清理测试通过")


def test_semantic_segmenter():
    """测试语义分段器"""
    print("\n" + "="*80)
    print("测试语义分段器")
    print("="*80)
    
    segmenter = SemanticSegmenter()
    
    # 测试1: 空内容
    segments = segmenter.segment("")
    assert segments == [], "空内容分段测试失败"
    print("✓ 空内容分段测试通过")
    
    # 测试2: 标题识别
    content = "第一章 概述\n这是第一章的内容\n第二章 详细设计\n这是第二章的内容"
    segments = segmenter.segment(content)
    assert len(segments) >= 2, "标题识别失败"
    print(f"✓ 标题识别测试通过，识别到{len(segments)}个分段")
    
    # 测试3: 句子分割
    content = "这是第一句。这是第二句！这是第三句？"
    sentences = segmenter.split_into_sentences(content)
    assert len(sentences) == 3, "句子分割失败"
    print(f"✓ 句子分割测试通过，分割出{len(sentences)}个句子")
    
    # 测试4: 关键点提取
    content = "因此，这是重要内容。普通内容。所以，这也是关键点。"
    key_points = segmenter.extract_key_points(content)
    assert len(key_points) >= 1, "关键点提取失败"
    print(f"✓ 关键点提取测试通过，提取到{len(key_points)}个关键点")


def test_hierarchy_builder():
    """测试层次结构构建器"""
    print("\n" + "="*80)
    print("测试层次结构构建器")
    print("="*80)
    
    builder = HierarchyBuilder()
    
    # 测试1: 空内容
    root = builder.build_hierarchy("", "test_doc")
    assert root.id == "test_doc_root", "空内容层次构建失败"
    assert root.title == "Root", "根节点标题错误"
    print("✓ 空内容层次构建测试通过")
    
    # 测试2: 层次结构构建
    content = "第一章 概述\n1.1 背景\n背景内容\n1.2 目标\n目标内容"
    root = builder.build_hierarchy(content, "test_doc")
    assert len(root.children) > 0, "层次结构构建失败"
    print(f"✓ 层次结构构建测试通过，共{len(root.children)}个一级节点")
    
    # 测试3: 目录生成
    toc = builder.build_table_of_contents(root)
    assert len(toc) > 0, "目录生成失败"
    print(f"✓ 目录生成测试通过，共{len(toc)}个目录项")
    
    # 测试4: 扁平化
    flat = builder.flatten_hierarchy(root)
    assert len(flat) > 0, "扁平化失败"
    print(f"✓ 扁平化测试通过，共{len(flat)}个节点")
    
    # 测试5: 序列化和反序列化
    root_dict = root.to_dict()
    restored_root = HierarchyNode.from_dict(root_dict)
    assert restored_root.id == root.id, "序列化/反序列化失败"
    print("✓ 序列化/反序列化测试通过")


def test_content_refiner():
    """测试内容提炼引擎"""
    print("\n" + "="*80)
    print("测试内容提炼引擎")
    print("="*80)
    
    refiner = ContentRefiner()
    
    # 测试1: 空内容
    result = refiner.refine_document("", "test_doc")
    assert result.original_content == "", "空内容提炼失败"
    print("✓ 空内容提炼测试通过")
    
    # 测试2: 完整提炼流程
    content = """
    第一章 概述
    
    本文档介绍了系统的设计。
    
    第1页
    
    1.1 背景
    
    随着数字化转型的推进，文档管理变得越来越重要。
    
    1.2 目标
    
    本文档的主要目标是提高效率。
    
    机密文档
    """
    
    result = refiner.refine_document(content, "test_doc")
    assert result.statistics['original_length'] > 0, "原始长度计算失败"
    assert len(result.hierarchy) > 0, "层次结构生成失败"
    assert 'noise_filter_stats' in result.statistics, "噪音过滤统计缺失"
    print(f"✓ 完整提炼流程测试通过")
    print(f"  - 原始长度: {result.statistics['original_length']}")
    print(f"  - 提炼后长度: {result.statistics['refined_length']}")
    print(f"  - 减少比例: {result.statistics['reduction_ratio']:.2f}%")
    
    # 测试3: 检索优化
    chunks = refiner.refine_for_retrieval(content, "test_doc", chunk_size=100)
    assert len(chunks) > 0, "检索优化失败"
    print(f"✓ 检索优化测试通过，生成{len(chunks)}个分块")
    
    # 测试4: 关键信息提取
    key_info = refiner.extract_key_information(content)
    assert 'key_points' in key_info, "关键信息提取失败"
    assert 'main_topics' in key_info, "主题提取失败"
    print(f"✓ 关键信息提取测试通过")
    print(f"  - 关键点数: {len(key_info['key_points'])}")
    print(f"  - 主题数: {len(key_info['main_topics'])}")


def test_integration():
    """测试集成功能"""
    print("\n" + "="*80)
    print("测试集成功能")
    print("="*80)
    
    refiner = ContentRefiner()
    
    # 模拟真实文档
    real_doc = """
    第一章 项目概述
    
    本文档详细介绍了文档管理系统的设计方案。
    
    1.1 项目背景
    
    随着企业数字化转型的深入推进，文档管理面临着巨大挑战。传统的纸质文档管理方式已经无法满足现代企业的需求。
    
    因此，我们需要构建一个智能化的文档管理系统。
    
    1.2 项目目标
    
    本项目的主要目标包括：
    - 提高文档处理效率
    - 降低人工成本
    - 提升文档安全性
    
    第二章 技术架构
    
    2.1 系统架构
    
    系统采用微服务架构，主要包含以下模块：
    - 文档上传模块
    - 内容提取模块
    - 向量化存储模块
    - 智能检索模块
    
    2.2 技术选型
    
    系统主要使用以下技术栈：
    - 后端框架：FastAPI
    - 向量数据库：ChromaDB
    - 嵌入模型：BGE中文模型
    
    第三章 实施方案
    
    3.1 实施步骤
    
    项目实施分为以下阶段：
    1. 需求分析
    2. 系统设计
    3. 开发实现
    4. 测试部署
    
    3.2 时间规划
    
    预计项目周期为3个月。
    
    第四章 总结
    
    本文档详细介绍了文档管理系统的设计方案。通过合理的架构设计和技术选型，系统能够满足企业的文档管理需求。
    
    第1页
    
    机密文档，仅供内部使用
    """
    
    # 完整提炼
    result = refiner.refine_document(real_doc, "integration_test")
    
    print(f"✓ 集成测试通过")
    print(f"  - 原始长度: {result.statistics['original_length']}")
    print(f"  - 提炼后长度: {result.statistics['refined_length']}")
    print(f"  - 减少比例: {result.statistics['reduction_ratio']:.2f}%")
    print(f"  - 层次节点数: {result.statistics['hierarchy_node_count']}")
    print(f"  - 层次深度: {result.statistics['hierarchy_depth']}")
    print(f"  - 分段数: {result.statistics['segment_count']}")
    
    # 验证噪音过滤效果
    assert "第1页" not in result.refined_content, "页码噪音未过滤"
    assert "机密文档" not in result.refined_content, "机密标识噪音未过滤"
    print("✓ 噪音过滤效果验证通过")
    
    # 验证层次结构
    assert result.statistics['hierarchy_node_count'] > 0, "层次结构未正确构建"
    print("✓ 层次结构验证通过")


def test_error_handling():
    """测试错误处理"""
    print("\n" + "="*80)
    print("测试错误处理")
    print("="*80)
    
    refiner = ContentRefiner()
    
    # 测试各种边界情况
    test_cases = [
        ("", "空字符串"),
        ("   ", "纯空格"),
        ("\n\n\n", "纯换行"),
        ("a", "单字符"),
        ("." * 1000, "重复字符"),
    ]
    
    for content, desc in test_cases:
        try:
            result = refiner.refine_document(content, "test")
            print(f"✓ {desc}测试通过")
        except Exception as e:
            print(f"✗ {desc}测试失败: {str(e)}")
            raise


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*80)
    print("开始运行所有测试")
    print("="*80)
    
    try:
        test_noise_filter()
        test_semantic_segmenter()
        test_hierarchy_builder()
        test_content_refiner()
        test_integration()
        test_error_handling()
        
        print("\n" + "="*80)
        print("✓ 所有测试通过！")
        print("="*80)
        
    except AssertionError as e:
        print(f"\n✗ 测试失败: {str(e)}")
        raise
    except Exception as e:
        print(f"\n✗ 测试异常: {str(e)}")
        raise


if __name__ == "__main__":
    run_all_tests()