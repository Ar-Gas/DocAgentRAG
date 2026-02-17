import json
import os
import uuid
from datetime import datetime
from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from .document_processor import process_document, process_pdf, process_word, process_excel, process_email

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOC_DIR = os.path.join(BASE_DIR, "doc")
CHROMA_DB_PATH = os.path.join(BASE_DIR, "chromadb")

# 确保必要的目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DOC_DIR, exist_ok=True)
os.makedirs(CHROMA_DB_PATH, exist_ok=True)

# 全局Chroma客户端实例
_chroma_client = None

# 保存文档信息到JSON
def save_document_info(doc_info):
    try:
        # 确保data目录存在
        os.makedirs(DATA_DIR, exist_ok=True)

        # 生成文件路径
        filepath = os.path.join(DATA_DIR, f"{doc_info['id']}.json")

        # 保存数据
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(doc_info, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        print(f"保存文档信息失败: {str(e)}")
        return False

# 获取文档信息
def get_document_info(document_id):
    try:
        filepath = os.path.join(DATA_DIR, f"{document_id}.json")

        if not os.path.exists(filepath):
            return None

        with open(filepath, 'r', encoding='utf-8') as f:
            doc_info = json.load(f)

        return doc_info
    except Exception as e:
        print(f"获取文档信息失败: {str(e)}")
        return None

# 保存分类结果
def save_classification_result(document_id, classification_result):
    try:
        filepath = os.path.join(DATA_DIR, f"{document_id}.json")

        if not os.path.exists(filepath):
            return False

        # 读取现有数据
        with open(filepath, 'r', encoding='utf-8') as f:
            doc_info = json.load(f)

        # 添加分类结果
        doc_info['classification_result'] = classification_result
        doc_info['classification_time'] = datetime.now().isoformat()

        # 保存更新后的数据
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(doc_info, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        print(f"保存分类结果失败: {str(e)}")
        return False

# 获取分类结果
def get_classification_result(document_id):
    try:
        doc_info = get_document_info(document_id)
        if not doc_info:
            return None

        return doc_info.get('classification_result', None)
    except Exception as e:
        print(f"获取分类结果失败: {str(e)}")
        return None

# 获取所有文档信息
def get_all_documents():
    try:
        documents = []

        if not os.path.exists(DATA_DIR):
            return documents

        for filename in os.listdir(DATA_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(DATA_DIR, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        doc_info = json.load(f)
                        documents.append(doc_info)
                except Exception as e:
                    print(f"读取文档{filename}失败: {str(e)}")
                    continue

        return documents
    except Exception as e:
        print(f"获取所有文档失败: {str(e)}")
        return []

# 初始化Chroma客户端
def init_chroma_client():
    """
    初始化Chroma客户端（使用本地模型，无需下载）
    """
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    try:
        # 使用本地模型路径（已下载好的模型）
        model_dir = '/root/autodl-tmp/DocAgentRAG/backend/models/all-MiniLM-L6-v2'
        
        # 使用本地模型初始化嵌入函数
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_dir,  # 直接用本地模型路径
            model_kwargs={'device': 'cpu'},  # 若有GPU可改为 'cuda'
            encode_kwargs={'normalize_embeddings': True}
        )
        
        # 3. 初始化Chroma客户端
        client = PersistentClient(path=CHROMA_DB_PATH)
        # 验证：创建集合时绑定本地嵌入函数
        client.get_or_create_collection(name="documents", embedding_function=ef)
        
        print(f"Chroma客户端初始化成功，使用本地模型：/root/autodl-tmp/DocAgentRAG/backend/models/all-MiniLM-L6-v2")
        _chroma_client = client
        return client
    except Exception as e:
        print(f"初始化Chroma客户端失败: {str(e)}")
        return None

# 保存文档摘要信息用于分类
def save_document_summary_for_classification(filepath):
    """
    读取文件名和文件前几页，放入json中，按合适的格式存储用于以后调用分类模型
    """
    try:
        # 生成文档ID
        document_id = str(uuid.uuid4())
        
        # 获取文件名
        filename = os.path.basename(filepath)
        
        # 获取文件扩展名
        ext = os.path.splitext(filepath)[1].lower()
        
        # 根据文件类型调用对应的处理函数
        if ext == '.pdf':
            content = process_pdf(filepath)
        elif ext == '.docx':
            content = process_word(filepath)
        elif ext in ['.xlsx', '.xls']:
            content = process_excel(filepath)
        elif ext in ['.eml', '.msg']:
            content = process_email(filepath)
        else:
            content = process_document(filepath)
        
        # 提取前几页内容（这里简化处理，取前1000个字符）
        preview_content = content[:1000]
        
        # 构建文档信息
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
        
        # 保存到JSON文件
        if save_document_info(doc_info):
            return document_id, doc_info
        else:
            return None, None
    except Exception as e:
        print(f"保存文档摘要失败: {str(e)}")
        return None, None

# 保存文档完整数据到Chroma用于检索
def save_document_to_chroma(filepath, document_id=None):
    """
    把文件的数据完整存入chroma，可以分段分句子都行，但是每个分片都要和文件名和doc内部路径对应，用于检索
    """
    try:
        # 初始化Chroma客户端（已适配魔门社区模型）
        client = init_chroma_client()
        if not client:
            return False
        
        # 如果没有提供document_id，生成一个新的
        if not document_id:
            document_id = str(uuid.uuid4())
        
        # 获取文件名
        filename = os.path.basename(filepath)
        
        # 获取文件扩展名
        ext = os.path.splitext(filepath)[1].lower()
        
        # 处理文档获取完整内容
        full_content = process_document(filepath)
        if not full_content:
            print(f"文档内容为空：{filepath}")
            return False
        
        # 分段处理（这里按句子分段，简化处理）
        chunks = []
        metadatas = []
        ids = []
        
        # 简单的句子分段（优化：避免空句子，处理中文句号）
        sentences = full_content.split('. ')
        # 兼容中文句号分割
        if len(sentences) <= 1:
            sentences = full_content.split('。')
        
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if sentence and len(sentence) > 1:  # 过滤空/极短句子
                chunk_id = f"{document_id}_chunk_{i}"
                chunks.append(sentence)
                metadatas.append({
                    'document_id': document_id,
                    'filename': filename,
                    'filepath': filepath,
                    'file_type': ext,
                    'chunk_index': i,
                    'doc_internal_path': f"{filename}#chunk_{i}"
                })
                ids.append(chunk_id)
        
        if not chunks:
            print(f"文档无有效分片：{filepath}")
            return False
        
        # 创建或获取集合（已绑定本地嵌入函数）
        collection = client.get_or_create_collection(name="documents")
        
        # 添加文档到Chroma（无外网模型下载，速度极快）
        collection.add(
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )
        
        print(f"文档保存成功：{filename}，共{len(chunks)}个分片")
        return True
    except Exception as e:
        print(f"保存文档到Chroma失败: {str(e)}")
        return False

# 从Chroma检索文档
def retrieve_from_chroma(query, n_results=5):
    """
    从Chroma检索相关文档
    """
    try:
        # 初始化Chroma客户端
        client = init_chroma_client()
        if not client:
            return []
        
        # 获取集合
        collection = client.get_or_create_collection(name="documents")
        
        # 执行检索
        results = collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        return results
    except Exception as e:
        print(f"从Chroma检索失败: {str(e)}")
        return []

# 删除文档
def delete_document(document_id):
    """
    删除文档及其相关信息
    """
    try:
        # 删除JSON文件
        json_file = os.path.join(DATA_DIR, f"{document_id}.json")
        if os.path.exists(json_file):
            os.remove(json_file)

        # 从Chroma中删除相关文档
        client = init_chroma_client()
        if client:
            collection = client.get_or_create_collection(name="documents")
            # 获取所有相关的chunk ID
            results = collection.get(where={"document_id": document_id})
            if results and results.get("ids"):
                collection.delete(ids=results["ids"])

        return True
    except Exception as e:
        print(f"删除文档失败: {str(e)}")
        return False

# 更新文档信息
def update_document_info(document_id, updated_info):
    """
    更新文档信息
    """
    try:
        doc_info = get_document_info(document_id)
        if not doc_info:
            return False

        # 更新信息
        doc_info.update(updated_info)
        doc_info['updated_at'] = datetime.now().isoformat()

        # 保存更新后的数据
        return save_document_info(doc_info)
    except Exception as e:
        print(f"更新文档信息失败: {str(e)}")
        return False

# 根据分类结果获取文档
def get_documents_by_classification(classification):
    """
    根据分类结果获取文档
    """
    try:
        all_docs = get_all_documents()
        filtered_docs = []
        for doc in all_docs:
            if doc.get('classification_result') == classification:
                filtered_docs.append(doc)
        return filtered_docs
    except Exception as e:
        print(f"根据分类获取文档失败: {str(e)}")
        return []
