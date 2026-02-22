import json
import os
import uuid
import threading
import logging
import requests
import base64
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union
from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

from .document_processor import (
    process_document, process_pdf, process_word,
    process_excel, process_email, process_ppt, process_image
)
from .content_refiner import ContentRefiner
from config import (
    DATA_DIR, DOC_DIR, CHROMA_DB_PATH, MODEL_DIR,
    MAX_CHUNK_LENGTH, MIN_CHUNK_LENGTH,
    DOUBAO_EMBEDDING_API_URL, DOUBAO_EMBEDDING_MODEL, DOUBAO_API_KEY
)

# 注意: multi_level_classifier 模块存在循环依赖（它导入了本模块的 get_all_documents）
# 因此相关函数使用延迟导入，在函数内部导入以避免循环导入错误

logger = logging.getLogger(__name__)

# ===================== 豆包多模态嵌入API =====================
def doubao_multimodal_embed(
    text: str, 
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None
) -> Optional[List[float]]:
    """
    调用豆包多模态嵌入API生成向量
    
    Args:
        text: 文本内容
        image_url: 图片URL（可选）
        image_base64: 图片base64编码（可选）
    
    Returns:
        嵌入向量列表，失败返回None
    """
    if not text and not image_url and not image_base64:
        logger.error("豆包嵌入失败：输入内容为空")
        return None
    
    try:
        input_data = []
        
        if text:
            input_data.append({
                "type": "text",
                "text": text
            })
        
        if image_url:
            input_data.append({
                "type": "image_url",
                "image_url": {
                    "url": image_url
                }
            })
        elif image_base64:
            input_data.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            })
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DOUBAO_API_KEY}"
        }
        
        payload = {
            "model": DOUBAO_EMBEDDING_MODEL,
            "input": input_data
        }
        
        response = requests.post(
            DOUBAO_EMBEDDING_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if "data" in result:
                data = result["data"]
                if isinstance(data, list) and len(data) > 0:
                    embedding = data[0].get("embedding")
                elif isinstance(data, dict):
                    embedding = data.get("embedding")
                else:
                    logger.error(f"豆包嵌入响应格式错误: {result}")
                    return None
                    
                if embedding:
                    logger.debug(f"豆包嵌入成功，向量维度: {len(embedding)}")
                    return embedding
                else:
                    logger.error(f"豆包嵌入响应缺少embedding字段: {result}")
                    return None
            else:
                logger.error(f"豆包嵌入响应格式错误: {result}")
                return None
        else:
            logger.error(f"豆包嵌入API调用失败: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("豆包嵌入API超时")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"豆包嵌入API请求异常: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"豆包嵌入处理异常: {str(e)}", exc_info=True)
        logger.error(f"异常类型: {type(e).__name__}, 异常详情: {repr(e)}")
        return None


def doubao_batch_embed(texts: List[str]) -> List[Optional[List[float]]]:
    """
    批量调用豆包嵌入API
    
    Args:
        texts: 文本列表
    
    Returns:
        嵌入向量列表
    """
    embeddings = []
    for text in texts:
        embedding = doubao_multimodal_embed(text)
        embeddings.append(embedding)
    return embeddings


class DoubaoEmbeddingFunction(EmbeddingFunction):
    """
    豆包嵌入函数类，兼容ChromaDB的EmbeddingFunction接口
    支持延迟加载回退模型（只在豆包API失败时才加载本地模型）
    """
    
    def __init__(self, fallback_model_name: Optional[str] = None):
        self._fallback_model_name = fallback_model_name
        self._fallback_ef = None
        self._use_doubao = True
        self._doubao_fail_count = 0
        self._max_fail_count = 3
        logger.info("DoubaoEmbeddingFunction 初始化完成（延迟加载回退模型）")
    
    def _get_fallback_ef(self):
        if self._fallback_ef is None and self._fallback_model_name:
            logger.info(f"正在加载回退模型: {self._fallback_model_name}")
            try:
                self._fallback_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=self._fallback_model_name
                )
                logger.info("回退模型加载成功")
            except Exception as e:
                logger.error(f"回退模型加载失败: {str(e)}")
        return self._fallback_ef
    
    def __call__(self, input: Documents) -> Embeddings:
        return self.embed_documents(input)
    
    def embed_documents(self, documents: Documents) -> Embeddings:
        if not documents:
            return []
        
        if self._use_doubao and self._doubao_fail_count < self._max_fail_count:
            embeddings = []
            all_success = True
            
            for doc in documents:
                embedding = doubao_multimodal_embed(doc)
                if embedding is None:
                    all_success = False
                    break
                embeddings.append(embedding)
            
            if all_success:
                self._doubao_fail_count = 0
                logger.info(f"豆包嵌入成功处理 {len(documents)} 个文档")
                return embeddings
            else:
                self._doubao_fail_count += 1
                logger.warning(f"豆包嵌入失败，失败计数: {self._doubao_fail_count}")
                
                if self._doubao_fail_count >= self._max_fail_count:
                    logger.warning("豆包嵌入连续失败次数过多，切换到回退模式")
                    self._use_doubao = False
        
        fallback_ef = self._get_fallback_ef()
        if fallback_ef:
            logger.info("使用回退嵌入函数")
            return fallback_ef(documents)
        
        raise RuntimeError("豆包嵌入不可用且未配置回退嵌入函数")
    
    def embed_query(self, query: str) -> List[float]:
        if self._use_doubao and self._doubao_fail_count < self._max_fail_count:
            embedding = doubao_multimodal_embed(query)
            if embedding is not None:
                self._doubao_fail_count = 0
                return embedding
            else:
                self._doubao_fail_count += 1
                if self._doubao_fail_count >= self._max_fail_count:
                    self._use_doubao = False
        
        fallback_ef = self._get_fallback_ef()
        if fallback_ef and hasattr(fallback_ef, 'embed_query'):
            return fallback_ef.embed_query(query)
        elif fallback_ef:
            results = fallback_ef([query])
            return results[0] if results else []
        
        raise RuntimeError("嵌入函数不可用")


def generate_document_embedding(document_id: str, content: str, image_paths: Optional[List[str]] = None) -> Optional[List[float]]:
    """
    生成文档级嵌入向量（支持多模态）
    
    Args:
        document_id: 文档ID
        content: 文档文本内容
        image_paths: 图片路径列表（可选）
    
    Returns:
        文档嵌入向量
    """
    if image_paths and len(image_paths) > 0:
        for img_path in image_paths:
            try:
                with open(img_path, 'rb') as f:
                    img_base64 = base64.b64encode(f.read()).decode('utf-8')
                embedding = doubao_multimodal_embed(content, image_base64=img_base64)
                if embedding:
                    logger.info(f"文档 {document_id} 多模态嵌入生成成功")
                    return embedding
            except Exception as e:
                logger.warning(f"处理图片 {img_path} 失败: {str(e)}")
                continue
    
    embedding = doubao_multimodal_embed(content)
    if embedding:
        logger.info(f"文档 {document_id} 文本嵌入生成成功")
    return embedding


def generate_paragraph_embeddings(document_id: str, paragraphs: List[dict]) -> List[dict]:
    """
    生成段落级嵌入向量
    
    Args:
        document_id: 文档ID
        paragraphs: 段落列表，每个段落包含 content 和可选的 style 信息
    
    Returns:
        带有嵌入向量的段落列表
    """
    result = []
    for i, para in enumerate(paragraphs):
        content = para.get('content', '')
        if not content:
            continue
        
        embedding = doubao_multimodal_embed(content)
        
        para_with_embedding = {
            **para,
            'embedding': embedding,
            'embedding_model': DOUBAO_EMBEDDING_MODEL if embedding else None,
            'paragraph_index': i
        }
        result.append(para_with_embedding)
    
    logger.info(f"文档 {document_id} 生成 {len(result)} 个段落嵌入")
    return result


def save_embeddings_to_json(document_id: str, doc_embedding: Optional[List[float]], 
                           paragraph_embeddings: Optional[List[dict]]) -> bool:
    """
    保存嵌入向量到JSON文件
    
    Args:
        document_id: 文档ID
        doc_embedding: 文档级嵌入
        paragraph_embeddings: 段落级嵌入列表
    
    Returns:
        是否保存成功
    """
    try:
        doc_info = get_document_info(document_id)
        if not doc_info:
            logger.error(f"保存嵌入失败：文档 {document_id} 不存在")
            return False
        
        doc_info['embeddings'] = {
            'document_embedding': doc_embedding,
            'paragraph_embeddings': paragraph_embeddings,
            'embedding_model': DOUBAO_EMBEDDING_MODEL,
            'embedding_time': datetime.now().isoformat()
        }
        
        return save_document_info(doc_info)
    except Exception as e:
        logger.error(f"保存嵌入到JSON失败: {str(e)}")
        return False

# ===================== 线程安全的单例客户端 =====================
_chroma_client = None
_chroma_collection = None
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
        EXCLUDED_FILES = {'classification_tree.json'}
        for filepath in json_files:
            if filepath.name in EXCLUDED_FILES:
                continue
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    doc_info = json.load(f)
                    if doc_info.get('id') and doc_info.get('filename'):
                        documents.append(doc_info)
                    else:
                        logger.warning(f"跳过无效文档文件: {filepath.name}")
            except Exception as e:
                logger.error(f"读取文档{filepath.name}失败: {str(e)}")
                continue
        return documents
    except Exception as e:
        logger.error(f"获取所有文档失败: {str(e)}")
        return []

# 初始化Chroma客户端
# 优先使用豆包多模态嵌入API，失败后回退到本地BGE模型
def init_chroma_client():
    global _chroma_client, _chroma_collection
    if _chroma_client is not None and _chroma_collection is not None:
        return _chroma_client, _chroma_collection
    with _client_lock:
        if _chroma_client is not None and _chroma_collection is not None:
            return _chroma_client, _chroma_collection
        
        client = PersistentClient(path=str(CHROMA_DB_PATH))
        
        try:
            logger.info("尝试使用豆包多模态嵌入API...")
            test_embedding = doubao_multimodal_embed("测试连接")
            
            if test_embedding is not None:
                bge_model = os.getenv('BGE_MODEL', 'BAAI/bge-small-zh-v1.5')
                logger.info(f"豆包API可用，回退模型配置: {bge_model}")
                
                doubao_ef = DoubaoEmbeddingFunction(fallback_model_name=bge_model)
                
                collection_exists = False
                try:
                    collection = client.get_collection(name="documents")
                    collection_exists = True
                    logger.info("检测到现有collection")
                except Exception:
                    collection_exists = False
                
                if collection_exists:
                    try:
                        test_doc = "维度测试文档"
                        collection.add(documents=[test_doc], ids=["dimension_test_temp"])
                        collection.delete(ids=["dimension_test_temp"])
                        logger.info("现有collection维度匹配")
                    except Exception as e:
                        if "dimension" in str(e).lower():
                            logger.warning(f"检测到维度不匹配，删除旧collection: {str(e)}")
                            client.delete_collection(name="documents")
                            collection_exists = False
                        else:
                            logger.warning(f"测试collection时出错: {str(e)}")
                
                if not collection_exists:
                    collection = client.create_collection(
                        name="documents",
                        embedding_function=doubao_ef
                    )
                
                logger.info("Chroma客户端初始化成功（使用豆包多模态嵌入API）")
                _chroma_client = client
                _chroma_collection = collection
                return client, collection
            else:
                raise Exception("豆包API测试失败")
                
        except Exception as doubao_error:
            logger.warning(f"豆包嵌入初始化出错: {str(doubao_error)}", exc_info=True)
            logger.info("回退到本地BGE嵌入模型...")
            
            try:
                bge_model = os.getenv('BGE_MODEL', 'BAAI/bge-small-zh-v1.5')
                logger.info(f"正在加载中文嵌入模型: {bge_model}")
                ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=bge_model
                )
                
                collection = client.get_or_create_collection(
                    name="documents",
                    embedding_function=ef
                )
                
                logger.info(f"Chroma客户端初始化成功（使用本地BGE模型: {bge_model}）")
                _chroma_client = client
                _chroma_collection = collection
                return client, collection
                
            except Exception as bge_error:
                logger.error(f"BGE模型加载失败: {str(bge_error)}")
                logger.warning("回退到默认嵌入函数...")
                
                try:
                    ef = embedding_functions.DefaultEmbeddingFunction()
                    collection = client.get_or_create_collection(
                        name="documents", 
                        embedding_function=ef
                    )
                    logger.info("Chroma客户端初始化成功（使用默认嵌入函数）")
                    _chroma_client = client
                    _chroma_collection = collection
                    return client, collection
                except Exception as fallback_error:
                    logger.error(f"兜底初始化也失败: {str(fallback_error)}")
                    return None, None


def get_chroma_collection():
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    _, collection = init_chroma_client()
    return collection
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
    filepath_path = Path(filepath) if filepath else None
    if not filepath_path or not filepath_path.exists():
        logger.error(f"保存摘要失败：文件不存在 {filepath}")
        return None, None
    try:
        document_id = str(uuid.uuid4())
        filename = filepath_path.name
        ext = filepath_path.suffix.lower()
        
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
        
        if ext in content_handlers:
            content = content_handlers[ext](filepath)
            if content.startswith("处理失败") or content.startswith("（扫描版PDF"):
                logger.error(f"文档内容无效：{filepath}")
                return None, None
        else:
            success, content = process_document(filepath)
            if not success:
                logger.error(f"文档内容无效：{filepath}")
                return None, None
        
        preview_content = content[:1000] if len(content) > 1000 else content
        mtime = filepath_path.stat().st_mtime
        doc_info = {
            'id': document_id,
            'filename': filename,
            'filepath': filepath,
            'file_type': ext,
            'preview_content': preview_content,
            'full_content_length': len(content),
            'created_at': mtime,
            'created_at_iso': datetime.fromtimestamp(mtime).isoformat()
        }
        if save_document_info(doc_info):
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

# 保存文档到Chroma（使用内容提炼引擎）
def save_document_to_chroma(filepath, document_id=None, use_refiner=True, save_chunk_info=True):
    filepath_path = Path(filepath) if filepath else None
    if not filepath_path or not filepath_path.exists():
        logger.error(f"保存失败：文件不存在 {filepath}")
        return False
    try:
        collection = get_chroma_collection()
        if not collection:
            return False
        document_id = document_id or str(uuid.uuid4())
        filename = filepath_path.name
        ext = filepath_path.suffix.lower()
        
        success, full_content = process_document(filepath)
        if not success:
            logger.error(f"文档内容无效：{filepath}")
            return False
        
        if use_refiner:
            try:
                refiner = ContentRefiner()
                chunks_data = refiner.refine_for_retrieval(full_content, document_id, chunk_size=MAX_CHUNK_LENGTH)
                chunks = [chunk['content'] for chunk in chunks_data]
                logger.info(f"使用提炼引擎优化内容: {filename}, 原始分片数{len(split_text_into_chunks(full_content))} -> 优化后{len(chunks)}")
            except Exception as e:
                logger.warning(f"提炼引擎处理失败，使用传统分块: {str(e)}")
                chunks = split_text_into_chunks(full_content)
        else:
            chunks = split_text_into_chunks(full_content)
        
        if not chunks:
            logger.error(f"无有效分片：{filepath}")
            return False
        
        # 保存分片信息到文档JSON
        if save_chunk_info:
            chunk_info = {
                'chunk_count': len(chunks),
                'chunk_size': MAX_CHUNK_LENGTH,
                'use_refiner': use_refiner,
                'chunked_at': datetime.now().isoformat(),
                'full_content_hash': hashlib.md5(full_content.encode('utf-8')).hexdigest()
            }
            update_document_info(document_id, {'chunk_info': chunk_info})
        
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
                'doc_internal_path': f"{filename}#chunk_{i}",
                'refined': use_refiner
            })
            ids.append(chunk_id)
        
        collection.add(documents=chunks, metadatas=metadatas, ids=ids)
        logger.info(f"文档保存成功：{filename}，共{len(chunks)}个分片")
        return True
    except Exception as e:
        logger.error(f"保存文档到Chroma失败: {str(e)}")
        return False


def re_chunk_document(document_id: str, use_refiner: bool = True) -> bool:
    """
    对文档进行重新分片，会删除旧的分片并重新生成
    
    Args:
        document_id: 文档ID
        use_refiner: 是否使用提炼引擎
    
    Returns:
        是否成功
    """
    try:
        doc_info = get_document_info(document_id)
        if not doc_info:
            logger.error(f"重新分片失败：文档 {document_id} 不存在")
            return False
        
        filename = doc_info.get('filename')
        filepath = doc_info.get('filepath')
        
        # 智能查找文件：如果原来的路径不存在，尝试在 classified_docs 目录中查找
        if not filepath or not Path(filepath).exists():
            logger.warning(f"原路径文件不存在，尝试查找文件：{filename}")
            
            # 查找文件的可能位置
            base_dir = Path(__file__).parent.parent
            possible_dirs = [
                base_dir / "classified_docs",
                base_dir / "doc"
            ]
            
            found_path = None
            for possible_dir in possible_dirs:
                if possible_dir.exists():
                    for p in possible_dir.rglob(filename):
                        if p.is_file():
                            found_path = str(p)
                            break
                    if found_path:
                        break
            
            if found_path:
                logger.info(f"找到文件：{found_path}")
                filepath = found_path
                # 更新文档信息中的 filepath
                update_document_info(document_id, {'filepath': filepath})
            else:
                logger.error(f"重新分片失败：无法找到文件 {filename}")
                return False
        
        collection = get_chroma_collection()
        if not collection:
            logger.error("重新分片失败：无法获取Chroma集合")
            return False
        
        # 删除旧分片
        try:
            results = collection.get(where={"document_id": document_id})
            if results and results.get("ids"):
                collection.delete(ids=results["ids"])
                logger.info(f"已删除旧分片：{len(results['ids'])}个")
        except Exception as e:
            logger.warning(f"删除旧分片时出错（可能不存在）: {str(e)}")
        
        # 重新保存到Chroma
        is_success = save_document_to_chroma(filepath, document_id=document_id, use_refiner=use_refiner)
        if is_success:
            logger.info(f"文档重新分片成功：{document_id}")
        return is_success
    except Exception as e:
        logger.error(f"重新分片失败: {str(e)}", exc_info=True)
        return False


def check_document_chunks(document_id: str) -> dict:
    """
    检查文档的分片状态
    
    Args:
        document_id: 文档ID
    
    Returns:
        包含分片状态信息的字典
    """
    try:
        doc_info = get_document_info(document_id)
        if not doc_info:
            return {
                'document_id': document_id,
                'exists': False,
                'has_chunks': False,
                'chunk_count': 0,
                'chunk_info': None
            }
        
        collection = get_chroma_collection()
        chunk_count = 0
        if collection:
            try:
                results = collection.get(where={"document_id": document_id})
                chunk_count = len(results.get('ids', [])) if results else 0
            except Exception as e:
                logger.warning(f"检查Chroma分片数量失败: {str(e)}")
        
        chunk_info = doc_info.get('chunk_info')
        
        return {
            'document_id': document_id,
            'exists': True,
            'has_chunks': chunk_count > 0,
            'chunk_count': chunk_count,
            'chunk_info': chunk_info,
            'in_sync': chunk_info and chunk_info.get('chunk_count') == chunk_count
        }
    except Exception as e:
        logger.error(f"检查文档分片状态失败: {str(e)}")
        return {
            'document_id': document_id,
            'exists': False,
            'has_chunks': False,
            'chunk_count': 0,
            'chunk_info': None,
            'error': str(e)
        }

# 从Chroma检索文档
def retrieve_from_chroma(query, n_results=5):
    if not query or n_results <= 0:
        logger.error("检索失败：查询为空或结果数非法")
        return []
    try:
        collection = get_chroma_collection()
        if not collection:
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
        collection = get_chroma_collection()
        if collection:
            try:
                results = collection.get(where={"document_id": document_id})
                if results and results.get("ids"):
                    collection.delete(ids=results["ids"])
            except Exception:
                pass
        
        update_classification_tree_after_delete(document_id)
        
        logger.info(f"文档{document_id}删除成功")
        return True
    except Exception as e:
        logger.error(f"删除文档失败: {str(e)}")
        return False

# 删除文档后更新分类树
def update_classification_tree_after_reclassify(document_id, old_classification, new_classification):
    """重新分类后更新分类树"""
    try:
        from utils.multi_level_classifier import get_multi_level_classifier
        
        classifier = get_multi_level_classifier()
        tree = classifier.load_classification_tree()
        
        if not tree or 'tree' not in tree:
            return
        
        doc_info = get_document_info(document_id)
        if not doc_info:
            return
        
        tree_modified = False
        
        if old_classification:
            for content_cat, types in list(tree['tree'].items()):
                for file_type, times in list(types.items()):
                    for time_group, docs in list(times.items()):
                        original_count = len(docs)
                        tree['tree'][content_cat][file_type][time_group] = [
                            doc for doc in docs 
                            if doc.get('document_id') != document_id
                        ]
                        new_count = len(tree['tree'][content_cat][file_type][time_group])
                        
                        if original_count != new_count:
                            tree_modified = True
                        
                        if not tree['tree'][content_cat][file_type][time_group]:
                            del tree['tree'][content_cat][file_type][time_group]
                    
                    if not tree['tree'][content_cat][file_type]:
                        del tree['tree'][content_cat][file_type]
                
                if not tree['tree'][content_cat]:
                    del tree['tree'][content_cat]
        
        if new_classification:
            content_cat = new_classification.get('content_category')
            file_type = new_classification.get('file_type')
            time_group = new_classification.get('time_group')
            
            if content_cat and file_type and time_group:
                if content_cat not in tree['tree']:
                    tree['tree'][content_cat] = {}
                if file_type not in tree['tree'][content_cat]:
                    tree['tree'][content_cat][file_type] = {}
                if time_group not in tree['tree'][content_cat][file_type]:
                    tree['tree'][content_cat][file_type][time_group] = []
                
                tree['tree'][content_cat][file_type][time_group].append(new_classification)
                tree_modified = True
        
        if tree_modified:
            tree['updated_at'] = datetime.now().isoformat()
            classifier.save_classification_tree(tree)
            logger.info(f"分类树已更新（重新分类）: {document_id}")
    except Exception as e:
        logger.error(f"重新分类后更新分类树失败: {str(e)}")

def update_classification_tree_after_delete(document_id):
    """删除文档后增量更新分类树"""
    try:
        from utils.multi_level_classifier import get_multi_level_classifier
        
        classifier = get_multi_level_classifier()
        tree = classifier.load_classification_tree()
        
        if not tree or 'tree' not in tree:
            return
        
        tree_modified = False
        for content_cat, types in list(tree['tree'].items()):
            for file_type, times in list(types.items()):
                for time_group, docs in list(times.items()):
                    original_count = len(docs)
                    tree['tree'][content_cat][file_type][time_group] = [
                        doc for doc in docs 
                        if doc.get('document_id') != document_id
                    ]
                    new_count = len(tree['tree'][content_cat][file_type][time_group])
                    
                    if original_count != new_count:
                        tree_modified = True
                    
                    if not tree['tree'][content_cat][file_type][time_group]:
                        del tree['tree'][content_cat][file_type][time_group]
                
                if not tree['tree'][content_cat][file_type]:
                    del tree['tree'][content_cat][file_type]
            
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