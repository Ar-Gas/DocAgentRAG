#!/usr/bin/env python3
import unittest
from unittest import mock
import tempfile
import shutil
import sys
from pathlib import Path

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.retriever import (
    search_documents,
    batch_search_documents,
    get_document_by_id,
    get_document_stats
)
from chromadb.errors import NotFoundError

class TestRetriever(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing (if needed)
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        # Clean up temporary directory
        shutil.rmtree(self.temp_dir)
    
    # ===================== 测试 search_documents =====================
    @mock.patch('utils.retriever.init_chroma_client')
    def test_search_documents_normal(self, mock_init_client):
        """测试正常搜索文档"""
        # Set up mocks
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock search results
        mock_results = {
            'metadatas': [[
                {'document_id': 'doc1', 'filename': 'test.pdf', 'filepath': '/path/to/test.pdf', 'file_type': '.pdf', 'chunk_index': 0},
                {'document_id': 'doc2', 'filename': 'test2.pdf', 'filepath': '/path/to/test2.pdf', 'file_type': '.pdf', 'chunk_index': 1}
            ]],
            'distances': [[0.2, 0.5]],
            'documents': [['这是测试文档内容', '这是另一个测试文档内容']]
        }
        mock_collection.query.return_value = mock_results
        
        # Test search
        results = search_documents("测试查询", limit=2)
        
        # Verify
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['document_id'], 'doc1')
        self.assertEqual(results[0]['similarity'], 0.8)  # 1 - 0.2
        self.assertEqual(results[1]['similarity'], 0.5)  # 1 - 0.5
        mock_collection.query.assert_called_once_with(
            query_texts=["测试查询"],
            n_results=2,
            include=["documents", "metadatas", "distances"]
        )
    
    def test_search_documents_invalid_params(self):
        """测试搜索文档的参数校验"""
        # Test empty query
        results = search_documents("", limit=10)
        self.assertEqual(results, [])
        
        # Test non-string query
        results = search_documents(123, limit=10)
        self.assertEqual(results, [])
        
        # Test limit <= 0
        results = search_documents("测试查询", limit=0)
        self.assertEqual(results, [])
        
        results = search_documents("测试查询", limit=-5)
        self.assertEqual(results, [])
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_search_documents_client_failed(self, mock_init_client):
        """测试搜索文档时客户端初始化失败"""
        mock_init_client.return_value = None
        results = search_documents("测试查询")
        self.assertEqual(results, [])
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_search_documents_collection_not_found(self, mock_init_client):
        """测试搜索文档时集合不存在"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.get_collection.side_effect = NotFoundError("Collection not found")
        
        results = search_documents("测试查询")
        self.assertEqual(results, [])
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_search_documents_incomplete_results(self, mock_init_client):
        """测试搜索文档时结果不完整"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock incomplete results (missing documents)
        mock_results = {
            'metadatas': [[{'document_id': 'doc1'}]],
            'distances': [[0.2]],
            'documents': [[]]  # Empty documents
        }
        mock_collection.query.return_value = mock_results
        
        results = search_documents("测试查询")
        self.assertEqual(results, [])
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_search_documents_metadata_none(self, mock_init_client):
        """测试搜索文档时元数据为空"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock results with None metadata
        mock_results = {
            'metadatas': [[None, {'document_id': 'doc2'}]],
            'distances': [[0.2, 0.5]],
            'documents': [['内容1', '内容2']]
        }
        mock_collection.query.return_value = mock_results
        
        results = search_documents("测试查询")
        self.assertEqual(len(results), 1)  # Only the second result is valid
        self.assertEqual(results[0]['document_id'], 'doc2')
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_search_documents_similarity_bounds(self, mock_init_client):
        """测试搜索文档时相似度边界限制"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock results with out-of-bounds distances
        mock_results = {
            'metadatas': [[
                {'document_id': 'doc1'},
                {'document_id': 'doc2'},
                {'document_id': 'doc3'}
            ]],
            'distances': [[-0.1, 0.5, 1.2]],  # Negative, normal, >1
            'documents': [['内容1', '内容2', '内容3']]
        }
        mock_collection.query.return_value = mock_results
        
        results = search_documents("测试查询")
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]['similarity'], 1.0)  # max(0, min(1, 1 - (-0.1)))
        self.assertEqual(results[1]['similarity'], 0.5)
        self.assertEqual(results[2]['similarity'], 0.0)  # max(0, min(1, 1 - 1.2))
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_search_documents_exception(self, mock_init_client):
        """测试搜索文档时发生异常"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.get_collection.side_effect = Exception("Test exception")
        
        results = search_documents("测试查询")
        self.assertEqual(results, [])
    
    # ===================== 测试 batch_search_documents =====================
    @mock.patch('utils.retriever.init_chroma_client')
    def test_batch_search_documents_normal(self, mock_init_client):
        """测试正常批量搜索文档"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock batch search results
        mock_results = {
            'metadatas': [
                [{'document_id': 'doc1'}],
                [{'document_id': 'doc2'}]
            ],
            'distances': [[0.2], [0.5]],
            'documents': [['内容1'], ['内容2']]
        }
        mock_collection.query.return_value = mock_results
        
        # Test batch search
        queries = ["查询1", "查询2"]
        results = batch_search_documents(queries, limit=1)
        
        # Verify
        self.assertEqual(len(results), 2)
        self.assertEqual(len(results[0]), 1)
        self.assertEqual(results[0][0]['document_id'], 'doc1')
        self.assertEqual(len(results[1]), 1)
        self.assertEqual(results[1][0]['document_id'], 'doc2')
    
    def test_batch_search_documents_invalid_params(self):
        """测试批量搜索文档的参数校验"""
        # Test non-list queries
        results = batch_search_documents("不是列表", limit=5)
        self.assertEqual(results, [])
        
        # Test empty list
        results = batch_search_documents([], limit=5)
        self.assertEqual(results, [])
        
        # Test limit <= 0
        results = batch_search_documents(["查询1"], limit=0)
        self.assertEqual(results, [])
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_batch_search_documents_client_failed(self, mock_init_client):
        """测试批量搜索文档时客户端初始化失败"""
        mock_init_client.return_value = None
        results = batch_search_documents(["查询1", "查询2"])
        self.assertEqual(results, [[], []])
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_batch_search_documents_collection_not_found(self, mock_init_client):
        """测试批量搜索文档时集合不存在"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.get_collection.side_effect = NotFoundError("Collection not found")
        
        results = batch_search_documents(["查询1", "查询2"])
        self.assertEqual(results, [[], []])
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_batch_search_documents_pad_empty_results(self, mock_init_client):
        """测试批量搜索文档时补全剩余查询的空结果"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock results with fewer queries than input
        mock_results = {
            'metadatas': [[{'document_id': 'doc1'}]],
            'distances': [[0.2]],
            'documents': [['内容1']]
        }
        mock_collection.query.return_value = mock_results
        
        # Test with 3 queries, but only 1 result
        results = batch_search_documents(["查询1", "查询2", "查询3"])
        self.assertEqual(len(results), 3)
        self.assertEqual(len(results[0]), 1)
        self.assertEqual(results[1], [])
        self.assertEqual(results[2], [])
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_batch_search_documents_exception(self, mock_init_client):
        """测试批量搜索文档时发生异常"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.get_collection.side_effect = Exception("Test exception")
        
        results = batch_search_documents(["查询1", "查询2"])
        self.assertEqual(results, [[], []])
    
    # ===================== 测试 get_document_by_id =====================
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_by_id_normal(self, mock_init_client):
        """测试正常根据ID获取文档"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock get results
        mock_results = {
            'metadatas': [{'document_id': 'doc1'}, {'document_id': 'doc1'}],
            'documents': ['内容1', '内容2'],
            'ids': ['chunk1', 'chunk2']
        }
        mock_collection.get.return_value = mock_results
        
        # Test get
        result = get_document_by_id("doc1")
        
        # Verify
        self.assertIsNotNone(result)
        self.assertEqual(len(result['chunks']), 2)
        self.assertEqual(len(result['metadatas']), 2)
        self.assertEqual(len(result['ids']), 2)
    
    def test_get_document_by_id_invalid_params(self):
        """测试根据ID获取文档的参数校验"""
        # Test empty ID
        result = get_document_by_id("")
        self.assertIsNone(result)
        
        # Test non-string ID
        result = get_document_by_id(123)
        self.assertIsNone(result)
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_by_id_client_failed(self, mock_init_client):
        """测试根据ID获取文档时客户端初始化失败"""
        mock_init_client.return_value = None
        result = get_document_by_id("doc1")
        self.assertIsNone(result)
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_by_id_collection_not_found(self, mock_init_client):
        """测试根据ID获取文档时集合不存在"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.get_collection.side_effect = NotFoundError("Collection not found")
        
        result = get_document_by_id("doc1")
        self.assertIsNone(result)
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_by_id_no_results(self, mock_init_client):
        """测试根据ID获取文档时无结果"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock empty results
        mock_results = {'metadatas': [], 'documents': [], 'ids': []}
        mock_collection.get.return_value = mock_results
        
        result = get_document_by_id("doc1")
        self.assertIsNone(result)
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_by_id_exception(self, mock_init_client):
        """测试根据ID获取文档时发生异常"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.get_collection.side_effect = Exception("Test exception")
        
        result = get_document_by_id("doc1")
        self.assertIsNone(result)
    
    # ===================== 测试 get_document_stats =====================
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_stats_normal(self, mock_init_client):
        """测试正常获取文档统计信息"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock count and get results
        mock_collection.count.return_value = 1500
        
        # Mock batch get results (for 1500 chunks, 2 batches)
        def mock_get(limit, offset, include):
            if offset == 0:
                return {
                    'metadatas': [
                        {'file_type': '.pdf'}, {'file_type': '.pdf'},
                        {'file_type': '.docx'}, {'file_type': '.docx'}, {'file_type': '.docx'}
                    ] * 200  # 1000 metadatas
                }
            elif offset == 1000:
                return {
                    'metadatas': [
                        {'file_type': '.xlsx'}, {'file_type': '.xlsx'},
                        {'file_type': '.pdf'}, None  # Test None metadata
                    ] * 125  # 500 metadatas
                }
            return {'metadatas': []}
        
        mock_collection.get.side_effect = mock_get
        
        # Test get stats
        stats = get_document_stats()
        
        # Verify
        self.assertEqual(stats['total_chunks'], 1500)
        self.assertEqual(stats['file_types']['.pdf'], 200*2 + 125*1)  # 525
        self.assertEqual(stats['file_types']['.docx'], 200*3)  # 600
        self.assertEqual(stats['file_types']['.xlsx'], 125*2)  # 250
        self.assertEqual(stats['file_types'].get('unknown', 0), 125*1)  # 125 (from None metadata)
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_stats_client_failed(self, mock_init_client):
        """测试获取文档统计信息时客户端初始化失败"""
        mock_init_client.return_value = None
        stats = get_document_stats()
        self.assertEqual(stats, {})
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_stats_collection_not_found(self, mock_init_client):
        """测试获取文档统计信息时集合不存在"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.get_collection.side_effect = NotFoundError("Collection not found")
        
        stats = get_document_stats()
        self.assertEqual(stats, {"total_chunks": 0, "file_types": {}})
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_stats_empty(self, mock_init_client):
        """测试获取文档统计信息时无数据"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        mock_collection.count.return_value = 0
        
        stats = get_document_stats()
        self.assertEqual(stats['total_chunks'], 0)
        self.assertEqual(stats['file_types'], {})
    
    @mock.patch('utils.retriever.init_chroma_client')
    def test_get_document_stats_exception(self, mock_init_client):
        """测试获取文档统计信息时发生异常"""
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.get_collection.side_effect = Exception("Test exception")
        
        stats = get_document_stats()
        self.assertEqual(stats, {})

if __name__ == '__main__':
    unittest.main()