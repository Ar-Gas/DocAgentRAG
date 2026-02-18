# 办公文档智能分类与检索系统 (DocAgentRAG)

## 项目概述

DocAgentRAG 是一个基于 RAG (Retrieval-Augmented Generation) 技术的办公文档智能管理系统，旨在帮助用户高效管理、分类和检索各类办公文档。

## 核心功能

- 📁 **文档管理**：支持上传、存储和管理多种格式的办公文档
- 🤖 **智能分类**：自动识别文档类型并进行分类
- 🔍 **向量检索**：基于语义相似度的文档检索
- 📄 **OCR 支持**：对扫描版 PDF 进行文字识别
- 📊 **数据分析**：文档统计和分析功能
- 🌐 **前后端分离**：现代化的 Web 界面和 RESTful API

## 技术栈

### 后端
- Python 3.8+
- FastAPI
- ChromaDB (向量数据库)
- Sentence-Transformers (文本嵌入)
- PyPDF2, python-docx, pandas (文档处理)
- pytesseract, Pillow (OCR 功能)
- scikit-learn (机器学习)

### 前端
- Vue 3
- Vite
- 现代化的前端框架和工具链

## 系统架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│   前端应用      │────▶│   后端 API      │────▶│   向量数据库    │
│  (Vue 3)        │     │  (FastAPI)      │     │  (ChromaDB)     │
│                 │◀────│                 │◀────│                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
          ▲                      ▲                      ▲
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  文件存储       │     │  文档处理       │     │  模型服务       │
│  (本地文件系统)  │     │  (OCR, 解析)    │     │  (文本嵌入)     │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## 目录结构

```
DocAgentRAG/
├── backend/            # 后端代码
│   ├── api/            # API 路由和控制器
│   ├── chromadb/       # ChromaDB 配置和管理
│   ├── data/           # 数据存储目录
│   ├── doc/            # 文档存储目录
│   ├── models/         # 模型相关代码
│   ├── test/           # 测试代码
│   ├── utils/          # 工具函数
│   ├── main.py         # 应用入口
│   └── requirements.txt # 依赖项
├── frontend/           # 前端代码
│   └── docagent-frontend/ # 前端应用
└── README.md           # 项目说明
```

## 快速开始

### 1. 环境准备

#### 后端环境

1. 确保安装了 Python 3.8 或更高版本
2. 安装 Tesseract OCR（用于扫描版 PDF 的文字识别）

   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install tesseract-ocr
   
   # CentOS/RHEL
   sudo yum install tesseract
   
   # macOS
   brew install tesseract
   ```

#### 前端环境

1. 确保安装了 Node.js 16 或更高版本
2. 安装 npm 或 yarn

### 2. 安装依赖

#### 后端依赖

```bash
cd backend
pip install -r requirements.txt
```

#### 前端依赖

```bash
cd frontend/docagent-frontend
npm install
# 或
yarn install
```

### 3. 启动服务

#### 启动后端服务

```bash
cd backend
# 开发模式
python main.py

# 生产模式
DEV_MODE=false python main.py
```

后端服务默认运行在 `http://localhost:6008`

#### 启动前端服务

```bash
cd frontend/docagent-frontend
npm run dev
# 或
yarn dev
```

前端服务默认运行在 `http://localhost:3000`

### 4. 访问系统

1. 打开浏览器，访问前端应用：`http://localhost:3000`
2. 或直接访问后端 API 文档：`http://localhost:6008/docs`

## API 文档

后端提供了完整的 RESTful API，可通过 Swagger UI 进行浏览和测试：

- **API 文档地址**：`http://localhost:6008/docs`
- **健康检查端点**：`http://localhost:6008/health`

## 功能使用指南

### 文档上传

1. 在前端应用中点击 "上传文档" 按钮
2. 选择要上传的文档文件
3. 系统会自动处理文档并添加到数据库

### 文档检索

1. 在搜索框中输入关键词或问题
2. 系统会基于语义相似度返回相关文档
3. 点击文档查看详细内容

### 文档分类

1. 上传文档后，系统会自动进行分类
2. 可在 "分类管理" 页面查看和管理分类
3. 支持手动调整文档分类

### OCR 功能

1. 上传扫描版 PDF 文档
2. 系统会自动进行 OCR 处理
3. 处理完成后可查看和搜索文档内容

## 配置说明

### 后端配置

- **端口**：默认 6008，可在 `main.py` 中修改
- **CORS**：默认允许所有来源，生产环境应修改为具体域名
- **存储路径**：默认使用项目内的 `data` 和 `doc` 目录

### 前端配置

- **API 地址**：默认指向 `http://localhost:6008/api`
- **端口**：默认 3000，可在 `vite.config.js` 中修改

## 性能优化

1. **模型缓存**：Sentence-Transformers 模型会被缓存，减少重复加载时间
2. **批量处理**：支持批量上传和处理文档
3. **异步操作**：使用 FastAPI 的异步特性提高并发处理能力

## 故障排查

### 常见问题

1. **OCR 失败**：确保已正确安装 Tesseract OCR
2. **模型加载失败**：检查网络连接，确保模型能够正常下载
3. **数据库连接失败**：确保 ChromaDB 配置正确

### 日志查看

后端日志会输出到控制台，包含详细的运行信息和错误提示。

## 部署建议

### 开发环境

- 使用默认配置即可，开启 `DEV_MODE` 获得热重载功能

### 生产环境

1. 设置 `DEV_MODE=false` 关闭热重载
2. 配置 CORS 为具体的前端域名
3. 考虑使用容器化部署（Docker）
4. 配置适当的服务器资源（内存、CPU）

## 未来规划

- [ ] 支持更多文档格式
- [ ] 增加文档版本控制
- [ ] 实现文档协作功能
- [ ] 添加多语言支持
- [ ] 优化模型性能和准确性
- [ ] 增加用户认证和权限管理

## 贡献指南

欢迎提交 Issue 和 Pull Request 来改进这个项目！

## 许可证

本项目采用 MIT 许可证。

## 联系方式

如有问题或建议，请通过以下方式联系：

- 项目地址：[DocAgentRAG](https://github.com/yourusername/DocAgentRAG)
- 电子邮件：your.email@example.com

---

**DocAgentRAG** - 让文档管理更智能、更高效！