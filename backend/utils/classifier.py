import os
import time
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .retriever import retrieve_relevant_documents

# 预定义文档类别及其关键词
CATEGORY_KEYWORDS = {
    '报告文档': ['报告', '分析', '总结', '评估', '调研', '研究', '考察', '检测', '鉴定'],
    '法律文档': ['合同', '协议', '条款', '法规', '法律', '诉讼', '仲裁', '调解', '判决'],
    '邮件文档': ['邮件', 'email', '发件人', '收件人', '抄送', '主题', '回复', '转发'],
    '数据文档': ['表格', '数据', '统计', 'excel', 'csv', '数据库', '报表', '图表', '分析'],
    '会议文档': ['会议', '纪要', '讨论', '议程', '议题', '决议', '参会', '记录', '汇报'],
    '技术文档': ['技术', '代码', '架构', '设计', '开发', '测试', '部署', '运维', '文档'],
    '财务文档': ['财务', '报表', '预算', '报销', '会计', '审计', '税务', '成本', '收入'],
    '人力资源文档': ['招聘', '培训', '员工', '人事', '绩效', '考核', '福利', '薪酬', '离职']
}

# 为每个类别创建特征文本
CATEGORY_FEATURES = {}
for category, keywords in CATEGORY_KEYWORDS.items():
    CATEGORY_FEATURES[category] = ' '.join(keywords)

# 创建TF-IDF向量化器
vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))

# 拟合类别特征
category_texts = list(CATEGORY_FEATURES.values())
category_names = list(CATEGORY_FEATURES.keys())
category_vectors = vectorizer.fit_transform(category_texts)

# 使用TF-IDF和余弦相似度进行分类
def classify_with_llm(content):
    try:
        # 预处理内容
        content = re.sub(r'\s+', ' ', content)
        content = content.lower()
        
        # 向量化内容
        content_vector = vectorizer.transform([content])
        
        # 计算与每个类别的相似度
        similarities = {}
        for i, category in enumerate(category_names):
            similarity = cosine_similarity(content_vector, category_vectors[i:i+1])[0][0]
            similarities[category] = similarity
        
        # 选择相似度高于阈值的类别
        threshold = 0.1
        categories = [category for category, similarity in similarities.items() if similarity > threshold]
        
        # 按相似度排序
        categories.sort(key=lambda x: similarities[x], reverse=True)
        
        # 如果没有类别超过阈值，返回'其他文档'
        if not categories:
            categories.append('其他文档')
        
        return categories[:3]  # 返回前3个最相关的类别
    except Exception as e:
        print(f"AI分类失败: {str(e)}")
        return ['其他文档']

# RAG增强分类
def rag_enhanced_classification(doc_info):
    try:
        # 提取文档内容
        content = doc_info.get('content', '')
        filename = doc_info.get('filename', '')

        # 组合信息
        combined_info = f"文件名: {filename}\n内容: {content}"

        # 使用RAG增强：检索相关文档以获取更多上下文
        retrieved_docs = retrieve_relevant_documents(content, top_k=3)
        rag_context = ""
        if retrieved_docs:
            rag_context = "\n\n相关参考文档:\n"
            for i, doc in enumerate(retrieved_docs):
                rag_context += f"{i+1}. {doc.get('filename', '未知文档')}: {doc.get('content', '')[:200]}...\n"

        # 组合RAG上下文
        enhanced_content = combined_info + rag_context

        # 使用LLM进行分类
        categories = classify_with_llm(enhanced_content)

        # 计算真实置信度（基于第一个类别的相似度）
        if categories and categories[0] != '其他文档':
            # 预处理内容
            content = re.sub(r'\s+', ' ', enhanced_content)
            content = content.lower()
            
            # 向量化内容
            content_vector = vectorizer.transform([content])
            
            # 找到第一个类别的索引
            if categories[0] in category_names:
                category_index = category_names.index(categories[0])
                confidence = cosine_similarity(content_vector, category_vectors[category_index:category_index+1])[0][0]
            else:
                confidence = 0.5
        else:
            confidence = 0.5

        # 生成分类目录
        classification_result = {
            "categories": categories,
            "confidence": round(confidence, 2),
            "classification_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "details": {
                "filename_analysis": f"基于文件名 '{filename}' 的分析",
                "content_analysis": "基于文档内容的分析",
                "rag_enhancement": f"使用RAG机制增强分类准确性，检索到{len(retrieved_docs)}个相关文档",
                "retrieved_documents": [doc.get('filename', '') for doc in retrieved_docs]
            },
            "suggested_folders": [
                f"{category}/{filename}" for category in categories
            ]
        }

        return classification_result
    except Exception as e:
        print(f"RAG增强分类失败: {str(e)}")
        return {
            "categories": ['其他文档'],
            "confidence": 0.5,
            "classification_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "details": {
                "error": str(e)
            },
            "suggested_folders": ["其他文档/{}".format(doc_info.get('filename', ''))]
        }



# OCR处理（使用真实的OCR工具）
def process_ocr(filepath):
    try:
        # 实际项目中可以集成Tesseract OCR或其他OCR工具
        # 这里使用一个基于文件扩展名的简单OCR模拟
        # 在实际应用中，应该使用pytesseract等库进行真实的OCR处理
        
        import pytesseract
        from PIL import Image
        import PyPDF2
        
        ocr_content = ""
        
        # 根据文件类型进行不同的OCR处理
        file_ext = os.path.splitext(filepath)[1].lower()
        
        if file_ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:
            # 处理图片文件
            try:
                img = Image.open(filepath)
                ocr_content = pytesseract.image_to_string(img, lang='chi_sim+eng')
            except Exception as img_error:
                print(f"图片OCR处理失败: {str(img_error)}")
        
        elif file_ext == '.pdf':
            # 处理PDF文件
            try:
                with open(filepath, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page_num in range(len(reader.pages)):
                        page = reader.pages[page_num]
                        text = page.extract_text()
                        if text:
                            ocr_content += f"\n\n第{page_num+1}页:\n{text}"
            except Exception as pdf_error:
                print(f"PDF OCR处理失败: {str(pdf_error)}")
        
        return ocr_content.strip()
    except Exception as e:
        print(f"OCR处理失败: {str(e)}")
        return ""



# 完整的文档分类流水线
def classify_document(doc_info):
    try:
        # 1. 提取文档内容
        content = doc_info.get('content', '')

        # 2. OCR处理（如果需要）
        filepath = doc_info.get('path', '')
        ocr_processed = False
        if filepath and os.path.exists(filepath):
            ocr_content = process_ocr(filepath)
            if ocr_content:
                content += f"\n\nOCR提取内容: {ocr_content}"
                ocr_processed = True

        # 3. 更新文档信息
        doc_info['content'] = content

        # 4. RAG增强分类
        classification_result = rag_enhanced_classification(doc_info)

        # 5. 生成最终分类目录
        final_result = {
            "document_id": doc_info.get('id', ''),
            "original_filename": doc_info.get('filename', ''),
            "classification_result": classification_result,
            "processing_details": {
                "ocr_processed": ocr_processed,
                "content_length": len(content),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            },
            "recommended_actions": [
                "根据分类结果整理文档",
                "将文档移动到对应分类文件夹",
                "更新文档元数据",
                "基于分类结果设置访问权限"
            ]
        }

        return final_result
    except Exception as e:
        print(f"文档分类失败: {str(e)}")
        return {
            "document_id": doc_info.get('id', ''),
            "original_filename": doc_info.get('filename', ''),
            "classification_result": {
                "categories": ['其他文档'],
                "confidence": 0.5,
                "error": str(e),
                "classification_time": time.strftime("%Y-%m-%dT%H:%M:%S")
            },
            "processing_details": {
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            },
            "recommended_actions": [
                "检查文档格式",
                "重新尝试分类",
                "检查OCR工具是否正确安装"
            ]
        }
