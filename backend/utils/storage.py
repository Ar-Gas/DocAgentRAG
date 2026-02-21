import json
import os
import uuid
import threading
import logging
from datetime import datetime
from pathlib import Path
from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from chromadb.errors import InvalidCollectionException

from .document_processor import (
    process_document, process_pdf, process_word,
    process_excel, process_email, process_ppt, process_image
)
from config import (
    DATA_DIR, DOC_DIR, CHROMA_DB_PATH, MODEL_DIR,
    MAX_CHUNK_LENGTH, MIN_CHUNK_LENGTH
)

logger = logging.getLogger(__name__)

# ===================== 线程安全的单例客户端 =====================
_chroma_client = None
_client_lock = threading.Lock()

# 保存文档信息到JSON
def save_document_info(doc_info):
    if not isinstance(doc_info, dict) or 'id' not in doc_info:
        logger.error("保存文档信息失败：无效的文档信息（缺少ID）")
        return False
    try:
        filepath = DATA_DIR / f"{doc_info['id']}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(doc_info, f, ensure_ascii=False, indent=2)
        logger.info(f"文档信息保存成功：{doc_info['id']}")
        return True
    except Exception as e:
        logger.error(f"保存文档信息失败: {str(e)}")
        return False

# 获取文档信息
def get_document_info(document_id):
    if not document_id or not isinstance(document_id, str):
        logger.error("获取文档信息失败：文档ID为空或非法")
        return None
    try:
        filepath = DATA_DIR / f"{document_id}.json"
        if not filepath.exists():
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            doc_info = json.load(f)
        return doc_info
    except Exception as e:
        logger.error(f"获取文档信息失败: {str(e)}")
        return None

# 保存分类结果
def save_classification_result(document_id, classification_result):
    if not document_id or not classification_result:
        logger.error("保存分类结果失败：ID或分类结果为空")
        return False
    try:
        filepath = DATA_DIR / f"{document_id}.json"
        if not filepath.exists():
            return False
        with open(filepath, 'r', encoding='utf-8') as f:
            doc_info = json.load(f)
        doc_info['classification_result'] = classification_result
        doc_info['classification_time'] = datetime.now().isoformat()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(doc_info, f, ensure_ascii=False, indent=2)
        logger.info(f"分类结果保存成功：{document_id}")
        return True
    except Exception as e:
        logger.error(f"保存分类结果失败: {str(e)}")
        return False

# 获取分类结果
def get_classification_result(document_id):
    try:
        doc_info = get_document_info(document_id)
        return doc_info.get('classification_result', None) if doc_info else None
    except Exception as e:
        logger.error(f"获取分类结果失败: {str(e)}")
        return None

# 获取所有文档信息
def get_all_documents():
    try:
        documents = []
        if not DATA_DIR.exists():
            return documents
        json_files = sorted(
            DATA_DIR.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        for filepath in json_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    doc_info = json.load(f)
                    documents.append(doc_info)
            except Exception as e:
                logger.error(f"读取文档{filepath.name}失败: {str(e)}")
                continue
        return documents
    except Exception as e:
        logger.error(f"获取所有文档失败: {str(e)}")
        return []

# 初始化Chroma客户端
# 使用支持中文的BGE嵌入模型
def init_chroma_client():
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    with _client_lock:
        if _chroma_client is not None:
            return _chroma_client
        try:
            # 使用支持中文的BGE模型
            # 可选模型: bge-small-zh-v1.5 (轻量), bge-base-zh-v1.5 (平衡), bge-large-zh-v1.5 (高性能)
            bge_model = os.getenv('BGE_MODEL', 'BAAI/bge-small-zh-v1.5')

            logger.info(f"正在加载中文嵌入模型: {bge_model}")
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=bge_model
            )

            # 初始化持久化客户端
            client = PersistentClient(path=str(CHROMA_DB_PATH))

            # 获取或创建集合
            collection = client.get_or_create_collection(
                name="documents",
                embedding_function=ef
            )

            logger.info(f"Chroma客户端初始化成功（使用中文嵌入模型: {bge_model}）")
            _chroma_client = client
            return client
        except InvalidCollectionException as e:
            logger.error(f"初始化失败：集合相关错误 - {str(e)}")
            return None
        except Exception as e:
            logger.error(f"初始化Chroma客户端失败: {str(e)}")
            # 兜底：使用默认嵌入函数
            logger.warning("回退到默认嵌入函数...")
            try:
                ef = embedding_functions.DefaultEmbeddingFunction()
                client = PersistentClient(path=str(CHROMA_DB_PATH))
                client.get_or_create_collection(name="documents", embedding_function=ef)
                logger.info("Chroma客户端初始化成功（使用默认嵌入函数）")
                _chroma_client = client
                return client
            except Exception as fallback_error:
                logger.error(f"兜底初始化也失败: {str(fallback_error)}")
                return None
# 智能分片函数
def split_text_into_chunks(text, max_length=MAX_CHUNK_LENGTH, min_length=MIN_CHUNK_LENGTH):
    if not text:
        return []
    chunks = []
    current_chunk = ""
    separators = ['。', '！', '？', '. ', '! ', '? ', '; ', '；', '\n']
    for sep in separators:
        if sep in text:
            sentences = text.split(sep)
            for sentence in sentences:
                sentence = sentence.strip() + sep
                if len(current_chunk + sentence) <= max_length:
                    current_chunk += sentence
                else:
                    if len(current_chunk) >= min_length:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence
            break
    else:
        for i in range(0, len(text), max_length):
            chunk = text[i:i+max_length].strip()
            if len(chunk) >= min_length:
                chunks.append(chunk)
    if len(current_chunk) >= min_length:
        chunks.append(current_chunk.strip())
    return chunks

# 保存文档摘要信息用于分类
def save_document_summary_for_classification(filepath):
    if not filepath or not os.path.exists(filepath):
        logger.error(f"保存摘要失败：文件不存在 {filepath}")
        return None, None
    try:
        document_id = str(uuid.uuid4())
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filepath)[1].lower()
        
        content_handlers = {
            '.pdf': process_pdf,
            '.docx': process_word,
            '.xlsx': process_excel,
            '.xls': process_excel,
            '.eml': process_email,
            '.msg': process_email,
            '.ppt': process_ppt,
            '.pptx': process_ppt,
            '.jpg': process_image,
            '.jpeg': process_image,
            '.png': process_image,
            '.gif': process_image,
            '.bmp': process_image,
            '.webp': process_image
        }
        
        # ===================== 修复：适配元组返回值 =====================
        if ext in content_handlers:
            # 单个处理器返回字符串
            content = content_handlers[ext](filepath)
            # 判断是否失败
            if content.startswith("处理失败") or content.startswith("（扫描版PDF"):
                logger.error(f"文档内容无效：{filepath}")
                return None, None
        else:
            # process_document 返回元组
            success, content = process_document(filepath)
            if not success:
                logger.error(f"文档内容无效：{filepath}")
                return None, None
        # =================================================================
        
        preview_content = content[:1000] if len(content) > 1000 else content
        doc_info = {
            'id': document_id,
            'filename': filename,
            'filepath': filepath,
            'file_type': ext,
            'preview_content': preview_content,
            'full_content_length': len(content),
            'created_at': os.path.getmtime(filepath),
            'created_at_iso': datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
        }
        if save_document_info(doc_info):
            # 新增文档后，增量更新分类树
            update_classification_tree_after_add(doc_info)
            return document_id, doc_info
        return None, None
    except Exception as e:
        logger.error(f"保存文档摘要失败: {str(e)}")
        return None, None

# 新增文档后更新分类树
def update_classification_tree_after_add(doc_info):
    """新增文档后增量更新分类树"""
    try:
        from utils.multi_level_classifier import get_multi_level_classifier, build_and_save_classification_tree
        
        classifier = get_multi_level_classifier()
        tree = classifier.load_classification_tree()
        
        if not tree or 'tree' not in tree:
            build_and_save_classification_tree()
            return
        
        # 对新文档进行分类
        classification = classifier.classify_document(doc_info)
        if not classification:
            return
        
        content_cat = classification['content_category']
        file_type = classification['file_type']
        time_group = classification['time_group']
        
        # 确保树结构存在
        if content_cat not in tree['tree']:
            tree['tree'][content_cat] = {}
        if file_type not in tree['tree'][content_cat]:
            tree['tree'][content_cat][file_type] = {}
        if time_group not in tree['tree'][content_cat][file_type]:
            tree['tree'][content_cat][file_type][time_group] = []
        
        # 添加新文档
        tree['tree'][content_cat][file_type][time_group].append(classification)
        tree['total_documents'] = tree.get('total_documents', 0) + 1
        tree['updated_at'] = datetime.now().isoformat()
        
        classifier.save_classification_tree(tree)
        logger.info(f"分类树已更新（新增文档）: {doc_info.get('filename')}")
    except Exception as e:
        logger.error(f"新增文档后更新分类树失败: {str(e)}")

# 保存文档到Chroma
def save_document_to_chroma(filepath, document_id=None):
    if not filepath or not os.path.exists(filepath):
        logger.error(f"保存失败：文件不存在 {filepath}")
        return False
    try:
        client = init_chroma_client()
        if not client:
            return False
        document_id = document_id or str(uuid.uuid4())
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filepath)[1].lower()
        
        # ===================== 修复：适配元组返回值 =====================
        success, full_content = process_document(filepath)
        if not success:
            logger.error(f"文档内容无效：{filepath}")
            return False
        # =================================================================
        
        chunks = split_text_into_chunks(full_content)
        if not chunks:
            logger.error(f"无有效分片：{filepath}")
            return False
        
        metadatas = []
        ids = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{document_id}_chunk_{i}"
            metadatas.append({
                'document_id': document_id,
                'filename': filename,
                'filepath': filepath,
                'file_type': ext,
                'chunk_index': i,
                'chunk_length': len(chunk),
                'doc_internal_path': f"{filename}#chunk_{i}"
            })
            ids.append(chunk_id)
        
        try:
            collection = client.get_collection(name="documents")
        except InvalidCollectionException:
            logger.error("集合不存在，请先初始化")
            return False
        
        collection.add(documents=chunks, metadatas=metadatas, ids=ids)
        logger.info(f"文档保存成功：{filename}，共{len(chunks)}个分片")
        return True
    except Exception as e:
        logger.error(f"保存文档到Chroma失败: {str(e)}")
        return False

# 从Chroma检索文档
def retrieve_from_chroma(query, n_results=5):
    if not query or n_results <= 0:
        logger.error("检索失败：查询为空或结果数非法")
        return []
    try:
        client = init_chroma_client()
        if not client:
            return []
        try:
            collection = client.get_collection(name="documents")
        except InvalidCollectionException:
            logger.warning("集合不存在，无检索结果")
            return []
        results = collection.query(query_texts=[query], n_results=n_results)
        return results
    except Exception as e:
        logger.error(f"从Chroma检索失败: {str(e)}")
        return []

# 删除文档
def delete_document(document_id):
    if not document_id:
        logger.error("删除失败：文档ID为空")
        return False
    try:
        json_file = DATA_DIR / f"{document_id}.json"
        if json_file.exists():
            json_file.unlink()
        client = init_chroma_client()
        if client:
            try:
                collection = client.get_collection(name="documents")
                results = collection.get(where={"document_id": document_id})
                if results and results.get("ids"):
                    collection.delete(ids=results["ids"])
            except InvalidCollectionException:
                pass
        
        # 更新分类树：移除删除的文档
        update_classification_tree_after_delete(document_id)
        
        logger.info(f"文档{document_id}删除成功")
        return True
    except Exception as e:
        logger.error(f"删除文档失败: {str(e)}")
        return False

# 删除文档后更新分类树
def update_classification_tree_after_delete(document_id):
    """删除文档后增量更新分类树"""
    try:
        from utils.multi_level_classifier import get_multi_level_classifier
        
        classifier = get_multi_level_classifier()
        tree = classifier.load_classification_tree()
        
        if not tree or 'tree' not in tree:
            return
        
        # 从树中移除该文档
        tree_modified = False
        for content_cat, types in list(tree['tree'].items()):
            for file_type, times in list(types.items()):
                for time_group, docs in list(times.items()):
                    # 过滤掉被删除的文档
                    original_count = len(docs)
                    tree['tree'][content_cat][file_type][time_group] = [
                        doc for doc in docs 
                        if doc.get('document_id') != document_id
                    ]
                    new_count = len(tree['tree'][content_cat][file_type][time_group])
                    
                    if original_count != new_count:
                        tree_modified = True
                    
                    # 如果该时间分组空了，移除
                    if not tree['tree'][content_cat][file_type][time_group]:
                        del tree['tree'][content_cat][file_type][time_group]
                
                # 如果该类型分组空了，移除
                if not tree['tree'][content_cat][file_type]:
                    del tree['tree'][content_cat][file_type]
            
            # 如果该内容分类空了，移除
            if not tree['tree'][content_cat]:
                del tree['tree'][content_cat]
        
        if tree_modified:
            tree['total_documents'] = max(0, tree.get('total_documents', 0) - 1)
            tree['updated_at'] = datetime.now().isoformat()
            classifier.save_classification_tree(tree)
            logger.info(f"分类树已更新（删除文档）: {document_id}")
    except Exception as e:
        logger.error(f"删除文档后更新分类树失败: {str(e)}")

# 更新文档信息
def update_document_info(document_id, updated_info):
    if not document_id or not isinstance(updated_info, dict):
        logger.error("更新失败：ID为空或更新信息非法")
        return False
    try:
        doc_info = get_document_info(document_id)
        if not doc_info:
            return False
        doc_info.update(updated_info)
        doc_info['updated_at'] = datetime.now().isoformat()
        return save_document_info(doc_info)
    except Exception as e:
        logger.error(f"更新文档信息失败: {str(e)}")
        return False

# 根据分类结果获取文档
def get_documents_by_classification(classification):
    if not classification:
        logger.error("分类过滤失败：分类标签为空")
        return []
    try:
        all_docs = get_all_documents()
        return [doc for doc in all_docs if doc.get('classification_result') == classification]
    except Exception as e:
        logger.error(f"根据分类获取文档失败: {str(e)}")
        return []