#!/usr/bin/env python3
import json
import os
import unittest
from unittest import mock
import tempfile
import shutil
from datetime import datetime
import uuid

# Add the backend directory to the path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.storage import (
    save_document_info,
    get_document_info,
    save_classification_result,
    get_classification_result,
    get_all_documents,
    init_chroma_client,
    save_document_summary_for_classification,
    save_document_to_chroma,
    retrieve_from_chroma,
    delete_document,
    update_document_info,
    get_documents_by_classification,
    BASE_DIR,
    DATA_DIR,
    DOC_DIR,
    CHROMA_DB_PATH
)

class TestStorage(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.test_data_dir = os.path.join(self.temp_dir, "data")
        os.makedirs(self.test_data_dir, exist_ok=True)
        
        # Mock the DATA_DIR and other paths
        global DATA_DIR, DOC_DIR, CHROMA_DB_PATH
        self.original_data_dir = DATA_DIR
        self.original_doc_dir = DOC_DIR
        self.original_chroma_db_path = CHROMA_DB_PATH
        
        # Override the paths for testing
        DATA_DIR = self.test_data_dir
        DOC_DIR = os.path.join(self.temp_dir, "doc")
        CHROMA_DB_PATH = os.path.join(self.temp_dir, "chromadb")
        
        # Mock the _chroma_client to None before each test
        from utils.storage import _chroma_client
        self.original_chroma_client = _chroma_client
        import utils.storage
        utils.storage._chroma_client = None
    
    def tearDown(self):
        # Restore original paths
        global DATA_DIR, DOC_DIR, CHROMA_DB_PATH
        DATA_DIR = self.original_data_dir
        DOC_DIR = self.original_doc_dir
        CHROMA_DB_PATH = self.original_chroma_db_path
        
        # Restore original chroma client
        import utils.storage
        utils.storage._chroma_client = self.original_chroma_client
        
        # Clean up temporary directory
        shutil.rmtree(self.temp_dir)
    
    def test_save_document_info(self):
        """Test saving document information to JSON"""
        doc_info = {
            "id": "test-doc-1",
            "filename": "test.pdf",
            "filepath": "/path/to/test.pdf",
            "file_type": ".pdf",
            "preview_content": "Test content",
            "full_content_length": 100,
            "created_at": 1620000000.0,
            "created_at_iso": "2021-05-03T12:00:00"
        }
        
        # Test successful save
        result = save_document_info(doc_info)
        self.assertTrue(result)
        
        # Verify the file was created
        expected_file = os.path.join(DATA_DIR, "test-doc-1.json")
        self.assertTrue(os.path.exists(expected_file))
        
        # Verify the content
        with open(expected_file, 'r', encoding='utf-8') as f:
            saved_info = json.load(f)
        self.assertEqual(saved_info, doc_info)
        
    def test_get_document_info(self):
        """Test getting document information from JSON"""
        # Create a test document info file
        doc_info = {
            "id": "test-doc-1",
            "filename": "test.pdf",
            "filepath": "/path/to/test.pdf"
        }
        
        # Save the document info
        with open(os.path.join(DATA_DIR, "test-doc-1.json"), 'w', encoding='utf-8') as f:
            json.dump(doc_info, f)
        
        # Test getting existing document
        result = get_document_info("test-doc-1")
        self.assertEqual(result, doc_info)
        
        # Test getting non-existent document
        result = get_document_info("non-existent-doc")
        self.assertIsNone(result)
    
    def test_save_classification_result(self):
        """Test saving classification result"""
        # Create a test document info file
        doc_info = {
            "id": "test-doc-1",
            "filename": "test.pdf",
            "filepath": "/path/to/test.pdf"
        }
        
        # Save the document info
        with open(os.path.join(DATA_DIR, "test-doc-1.json"), 'w', encoding='utf-8') as f:
            json.dump(doc_info, f)
        
        # Test saving classification result
        classification_result = "financial"
        result = save_classification_result("test-doc-1", classification_result)
        self.assertTrue(result)
        
        # Verify the classification result was saved
        with open(os.path.join(DATA_DIR, "test-doc-1.json"), 'r', encoding='utf-8') as f:
            updated_info = json.load(f)
        self.assertEqual(updated_info.get('classification_result'), classification_result)
        self.assertIn('classification_time', updated_info)
        
        # Test saving classification result for non-existent document
        result = save_classification_result("non-existent-doc", "financial")
        self.assertFalse(result)
    
    def test_get_classification_result(self):
        """Test getting classification result"""
        # Create a test document info file with classification
        doc_info = {
            "id": "test-doc-1",
            "filename": "test.pdf",
            "filepath": "/path/to/test.pdf",
            "classification_result": "financial"
        }
        
        # Save the document info
        with open(os.path.join(DATA_DIR, "test-doc-1.json"), 'w', encoding='utf-8') as f:
            json.dump(doc_info, f)
        
        # Test getting existing classification
        result = get_classification_result("test-doc-1")
        self.assertEqual(result, "financial")
        
        # Test getting classification for non-existent document
        result = get_classification_result("non-existent-doc")
        self.assertIsNone(result)
    
    def test_get_all_documents(self):
        """Test getting all documents"""
        # Create multiple test document info files
        doc1 = {
            "id": "test-doc-1",
            "filename": "test1.pdf",
            "filepath": "/path/to/test1.pdf"
        }
        
        doc2 = {
            "id": "test-doc-2",
            "filename": "test2.pdf",
            "filepath": "/path/to/test2.pdf"
        }
        
        # Save the document info files
        with open(os.path.join(DATA_DIR, "test-doc-1.json"), 'w', encoding='utf-8') as f:
            json.dump(doc1, f)
        
        with open(os.path.join(DATA_DIR, "test-doc-2.json"), 'w', encoding='utf-8') as f:
            json.dump(doc2, f)
        
        # Test getting all documents
        result = get_all_documents()
        self.assertEqual(len(result), 2)
        self.assertIn(doc1, result)
        self.assertIn(doc2, result)
    
    @mock.patch('utils.storage.embedding_functions.SentenceTransformerEmbeddingFunction')
    @mock.patch('utils.storage.PersistentClient')
    def test_init_chroma_client(self, mock_client_class, mock_embedding_function):
        """Test initializing Chroma client"""
        # Set up mocks
        mock_client = mock.MagicMock()
        mock_client_class.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        
        # Test initializing client
        result = init_chroma_client()
        self.assertEqual(result, mock_client)
        
        # Verify the client was created with the correct path
        mock_client_class.assert_called_once_with(path=CHROMA_DB_PATH)
        
        # Test that the client is cached
        second_result = init_chroma_client()
        self.assertEqual(second_result, mock_client)
        # Should only be called once
        mock_client_class.assert_called_once()
    
    @mock.patch('utils.storage.process_document')
    @mock.patch('utils.storage.process_pdf')
    @mock.patch('utils.storage.process_word')
    @mock.patch('utils.storage.process_excel')
    @mock.patch('utils.storage.process_email')
    @mock.patch('utils.storage.save_document_info')
    @mock.patch('os.path.getmtime')
    def test_save_document_summary_for_classification(self, mock_getmtime, mock_save_doc, mock_process_email, mock_process_excel, mock_process_word, mock_process_pdf, mock_process_doc):
        """Test saving document summary for classification"""
        # Set up mocks
        mock_getmtime.return_value = 1620000000.0
        mock_save_doc.return_value = True
        
        # Test PDF file
        mock_process_pdf.return_value = "PDF content"
        doc_id, doc_info = save_document_summary_for_classification("test.pdf")
        self.assertIsNotNone(doc_id)
        self.assertIsNotNone(doc_info)
        mock_process_pdf.assert_called_once_with("test.pdf")
        
        # Test Word file
        mock_process_pdf.reset_mock()
        mock_process_word.return_value = "Word content"
        doc_id, doc_info = save_document_summary_for_classification("test.docx")
        self.assertIsNotNone(doc_id)
        self.assertIsNotNone(doc_info)
        mock_process_word.assert_called_once_with("test.docx")
        
        # Test Excel file
        mock_process_word.reset_mock()
        mock_process_excel.return_value = "Excel content"
        doc_id, doc_info = save_document_summary_for_classification("test.xlsx")
        self.assertIsNotNone(doc_id)
        self.assertIsNotNone(doc_info)
        mock_process_excel.assert_called_once_with("test.xlsx")
        
        # Test email file
        mock_process_excel.reset_mock()
        mock_process_email.return_value = "Email content"
        doc_id, doc_info = save_document_summary_for_classification("test.eml")
        self.assertIsNotNone(doc_id)
        self.assertIsNotNone(doc_info)
        mock_process_email.assert_called_once_with("test.eml")
        
        # Test other file types
        mock_process_email.reset_mock()
        mock_process_doc.return_value = "Other content"
        doc_id, doc_info = save_document_summary_for_classification("test.txt")
        self.assertIsNotNone(doc_id)
        self.assertIsNotNone(doc_info)
        mock_process_doc.assert_called_once_with("test.txt")
    
    @mock.patch('utils.storage.init_chroma_client')
    @mock.patch('utils.storage.process_document')
    def test_save_document_to_chroma(self, mock_process_doc, mock_init_client):
        """Test saving document to Chroma"""
        # Set up mocks
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_process_doc.return_value = "Test content. More content."
        
        # Test saving document
        result = save_document_to_chroma("test.txt")
        self.assertTrue(result)
        
        # Verify the collection was called with chunks
        mock_collection.add.assert_called_once()
        call_args = mock_collection.add.call_args
        self.assertIn('documents', call_args.kwargs)
        self.assertIn('metadatas', call_args.kwargs)
        self.assertIn('ids', call_args.kwargs)
    
    @mock.patch('utils.storage.init_chroma_client')
    def test_retrieve_from_chroma(self, mock_init_client):
        """Test retrieving from Chroma"""
        # Set up mocks
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_results = {"documents": [["Result 1", "Result 2"]]}
        mock_collection.query.return_value = mock_results
        
        # Test retrieval
        results = retrieve_from_chroma("test query")
        self.assertEqual(results, mock_results)
        mock_collection.query.assert_called_once_with(query_texts=["test query"], n_results=5)
    
    @mock.patch('utils.storage.init_chroma_client')
    @mock.patch('os.remove')
    @mock.patch('os.path.exists')
    def test_delete_document(self, mock_exists, mock_remove, mock_init_client):
        """Test deleting document"""
        # Set up mocks
        mock_exists.return_value = True
        mock_client = mock.MagicMock()
        mock_init_client.return_value = mock_client
        mock_collection = mock.MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_collection.get.return_value = {"ids": ["chunk1", "chunk2"]}
        
        # Test deletion
        result = delete_document("test-doc-1")
        self.assertTrue(result)
        mock_remove.assert_called_once()
        mock_collection.delete.assert_called_once_with(ids=["chunk1", "chunk2"])
    
    @mock.patch('utils.storage.get_document_info')
    @mock.patch('utils.storage.save_document_info')
    def test_update_document_info(self, mock_save_doc, mock_get_doc):
        """Test updating document information"""
        # Set up mocks
        existing_doc = {
            "id": "test-doc-1",
            "filename": "old_name.pdf",
            "filepath": "/path/to/old_name.pdf"
        }
        mock_get_doc.return_value = existing_doc
        mock_save_doc.return_value = True
        
        # Test update
        updated_info = {"filename": "new_name.pdf", "filepath": "/path/to/new_name.pdf"}
        result = update_document_info("test-doc-1", updated_info)
        self.assertTrue(result)
        
        # Verify save was called with updated info
        mock_save_doc.assert_called_once()
        saved_doc = mock_save_doc.call_args[0][0]
        self.assertEqual(saved_doc["filename"], "new_name.pdf")
        self.assertEqual(saved_doc["filepath"], "/path/to/new_name.pdf")
        self.assertIn('updated_at', saved_doc)
    
    @mock.patch('utils.storage.get_all_documents')
    def test_get_documents_by_classification(self, mock_get_all):
        """Test getting documents by classification"""
        # Set up mocks
        mock_get_all.return_value = [
            {"id": "doc1", "classification_result": "financial"},
            {"id": "doc2", "classification_result": "legal"},
            {"id": "doc3", "classification_result": "financial"}
        ]
        
        # Test getting financial documents
        result = get_documents_by_classification("financial")
        self.assertEqual(len(result), 2)
        for doc in result:
            self.assertEqual(doc["classification_result"], "financial")

if __name__ == '__main__':
    unittest.main()
