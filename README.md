# DocAgentRAG

办公文档智能分类与检索系统，基于RAG（检索增强生成）技术实现。

## 项目结构

项目采用前后端分离架构：

```
DocAgentRAG/
├── frontend/          # 前端项目
│   ├── dist/          # 前端构建产物
│   ├── src/           # 前端源代码
│   ├── package.json   # 前端依赖配置
│   └── vite.config.js # Vite配置文件
├── backend/           # 后端项目
│   ├── api/           # API路由
│   ├── utils/         # 工具函数
│   ├── data/          # 数据存储
│   ├── doc/           # 文档存储
│   ├── chromadb/      # 向量数据库
│   ├── main.py        # 后端入口文件
│   └── requirements.txt # 后端依赖配置
└── README.md          # 项目说明文档
```

## 技术栈

### 前端
- Vue 3
- Vite
- Axios
- Pinia（状态管理）
- Vue Router

### 后端
- Python 3.12
- FastAPI
- ChromaDB（向量数据库）
- Sentence Transformers（文本向量化）
- python-docx、pandas、openpyxl（文档处理）

## 功能特性

1. **文档上传**：支持多种格式文档上传
2. **智能分类**：自动识别文档类型并分类
3. **向量检索**：基于语义的文档搜索
4. **文件管理**：树形结构展示文档
5. **搜索结果**：显示相关性评分和内容摘要

## 安装与运行

### 前端

1. 进入前端目录
   ```bash
   cd frontend
   ```

2. 安装依赖
   ```bash
   npm install
   ```

3. 启动开发服务器
   ```bash
   npm run dev
   ```

4. 构建生产版本
   ```bash
   npm run build
   ```

前端开发服务器默认运行在 `http://localhost:5173`

### 后端

1. 进入后端目录
   ```bash
   cd backend
   ```

2. 安装依赖
   ```bash
   pip install -r requirements.txt
   ```

3. 启动后端服务器
   ```bash
   python main.py
   ```

后端服务器默认运行在 `http://localhost:6008`

## API文档

后端提供了完整的API文档，可通过以下地址访问：
- `http://localhost:6008/docs` - Swagger UI
- `http://localhost:6008/redoc` - ReDoc

## 注意事项

1. 首次运行时，系统会自动创建必要的目录结构
2. 后端需要较大的内存用于文本向量化和向量检索
3. 生产环境部署时，应修改CORS配置，限制允许的前端域名

## 许可证

本项目仅供毕业设计使用，禁止商用。
