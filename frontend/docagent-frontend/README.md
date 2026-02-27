# DocAgentRAG 前端应用

基于 Vue 3 + Vite + Element Plus 构建的办公文档智能管理系统前端应用。

## 技术栈

- **框架**: Vue 3.5 (Composition API)
- **构建工具**: Vite 7
- **UI 组件库**: Element Plus 2.13
- **路由**: Vue Router 5
- **HTTP 客户端**: Axios 1.13
- **样式**: SCSS

## 项目结构

```
src/
├── api/                    # API 请求封装
├── assets/                 # 静态资源
├── components/             # Vue 组件
│   ├── FileUpload.vue     # 文件上传组件
│   ├── SearchBox.vue      # 搜索框组件
│   ├── FileList.vue       # 文件列表组件
│   ├── ClassificationPanel.vue  # 分类面板组件
│   ├── MultiLevelClassification.vue  # 多级分类组件
│   └── SearchResultDialog.vue  # 搜索结果弹窗
├── views/                  # 页面视图
├── router/                 # 路由配置
├── App.vue                 # 根组件
├── main.js                 # 入口文件
└── style.css              # 全局样式
```

## 核心功能模块

### 1. 文件上传 (FileUpload)

- 支持拖拽上传
- 支持多种文档格式（PDF、Word、Excel、PPT、图片等）
- 上传进度显示
- 上传成功/失败提示

### 2. 文档检索 (SearchBox)

支持多种检索模式：

- **语义检索**: 基于向量相似度
- **混合检索**: 向量 + BM25 关键词
- **智能检索**: LLM 查询扩展 + 重排序
- **多模态检索**: 文本 + 图片

### 3. 文档列表 (FileList)

- 分页展示文档
- 文档预览
- 分类状态显示
- 批量操作支持

### 4. 文档分类

#### 旧版分类 (ClassificationPanel)
- 单文档分类
- 批量分类
- 分类目录创建

#### 多级分类 (MultiLevelClassification)
- 三级分类树：内容 → 类型 → 时间
- 树形结构展示
- 按分类筛选文档

### 5. 搜索结果弹窗 (SearchResultDialog)

- 检索结果列表
- 关键词高亮
- 相似度显示
- 切换检索类型

## 开发指南

### 环境要求

- Node.js 20+
- npm 或 yarn

### 安装依赖

```bash
npm install
```

### 开发模式

```bash
npm run dev
```

访问 http://localhost:3000

### 生产构建

```bash
npm run build
```

### 预览构建结果

```bash
npm run preview
```

## 配置说明

### Vite 配置 (vite.config.js)

```javascript
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:6008',
        changeOrigin: true,
        rewrite: (path) => path
      }
    }
  }
})
```

### API 代理

开发环境下，前端请求 `/api/*` 会自动代理到后端 `http://localhost:6008`。

## API 接口调用

### 文档管理

```javascript
import { api } from '@/api'

// 获取文档列表
await api.getDocumentList(page, pageSize)

// 上传文档
await api.uploadDocument(formData)

// 删除文档
await api.deleteDocument(documentId)

// 获取文档详情
await api.getDocumentDetail(documentId)
```

### 检索服务

```javascript
// 语义检索
await api.searchDocuments(query, limit)

// 混合检索
await api.hybridSearch(query, options)

// 智能检索
await api.smartSearch(query, options)

// 多模态检索
await api.multimodalSearch(query, imageFile, options)
```

### 分类服务

```javascript
// 单文档分类
await api.classifyDocument(documentId)

// 获取分类列表
await api.getCategories()

// 构建多级分类树
await api.buildClassificationTree()

// 获取分类下文档
await api.getDocumentsByCategory(category)
```

## 组件使用示例

### 文件上传

```vue
<template>
  <FileUpload @upload-success="handleUploadSuccess" />
</template>

<script setup>
import FileUpload from '@/components/FileUpload.vue'

const handleUploadSuccess = () => {
  // 刷新文档列表
  loadDocuments()
}
</script>
```

### 搜索框

```vue
<template>
  <SearchBox 
    :stats="stats" 
    @search-result="handleSearchResult"
    @search-query="handleSearchQuery"
  />
</template>

<script setup>
import SearchBox from '@/components/SearchBox.vue'

const handleSearchResult = (results) => {
  // 处理搜索结果
  console.log(results)
}
</script>
```

## 样式规范

- 使用 SCSS 预处理器
- 遵循 BEM 命名规范
- 响应式设计（支持移动端）
- Element Plus 主题定制

## 响应式设计

```scss
// 平板适配
@media (max-width: 1024px) {
  .top-section {
    grid-template-columns: 1fr;
  }
}

// 移动端适配
@media (max-width: 768px) {
  .page-header h1 {
    font-size: 24px;
  }
}
```

## 部署

### 静态部署

```bash
# 构建
npm run build

# 生成的 dist 目录可部署到任何静态服务器
```

### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        root /path/to/dist;
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://localhost:6008;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 浏览器支持

- Chrome (推荐)
- Firefox
- Safari
- Edge

## 常见问题

### Q: 开发环境跨域问题？

Vite 已配置代理，开发时无需处理跨域。

### Q: 上传大文件失败？

检查后端 `MAX_FILE_SIZE` 配置，默认 500MB。

### Q: 样式不生效？

检查 SCSS 变量是否正确引入，确保 `lang="scss"` 属性存在。
