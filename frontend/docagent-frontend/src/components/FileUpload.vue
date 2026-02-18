<template>
  <div class="card upload-card">
    <div class="card-header">
      <el-icon><Upload /></el-icon>
      <span>文档上传</span>
    </div>
    <el-upload
      class="upload-demo"
      drag
      :auto-upload="false"
      :on-change="handleFileChange"
      :show-file-list="false"
      accept=".pdf,.docx,.doc,.xlsx,.xls,.ppt,.pptx,.eml,.msg,.txt"
    >
      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
      <div class="el-upload__text">
        将文件拖到此处，或<em>点击上传</em>
      </div>
      <template #tip>
        <div class="el-upload__tip">
          支持 pdf, docx, xlsx, ppt, eml, txt 等格式，最大 50MB
        </div>
      </template>
    </el-upload>
  </div>
</template>

<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, UploadFilled } from '@element-plus/icons-vue'
import { api } from '@/api'

// 向父组件发送事件：上传成功后刷新列表
const emit = defineEmits(['upload-success'])

// 上传逻辑
const handleFileChange = async (file) => {
  try {
    // 二次确认
    await ElMessageBox.confirm(`确定要上传文件 "${file.name}" 吗？`, '上传确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'info'
    })
    
    // 调用上传API
    await api.uploadFile(file.raw)
    ElMessage.success('文件上传成功！')
    // 通知父组件刷新数据
    emit('upload-success')
  } catch (error) {
    // 忽略用户取消的情况
    if (error !== 'cancel') {
      console.error('上传失败：', error)
    }
  }
}
</script>

<style scoped lang="scss">
.upload-card {
  .el-upload-dragger {
    width: 100%;
    height: 200px;
  }
}
</style>