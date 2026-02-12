import json
import os

# 保存文档信息到JSON
def save_document_info(doc_info):
    try:
        # 确保data目录存在
        os.makedirs("data", exist_ok=True)
        
        # 生成文件路径
        filepath = os.path.join("data", f"{doc_info['id']}.json")
        
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
        filepath = os.path.join("data", f"{document_id}.json")
        
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
        filepath = os.path.join("data", f"{document_id}.json")
        
        if not os.path.exists(filepath):
            return False
        
        # 读取现有数据
        with open(filepath, 'r', encoding='utf-8') as f:
            doc_info = json.load(f)
        
        # 添加分类结果
        doc_info['classification_result'] = classification_result
        
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
        data_dir = "data"
        
        if not os.path.exists(data_dir):
            return documents
        
        for filename in os.listdir(data_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(data_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    doc_info = json.load(f)
                    documents.append(doc_info)
        
        return documents
    except Exception as e:
        print(f"获取所有文档失败: {str(e)}")
        return []
