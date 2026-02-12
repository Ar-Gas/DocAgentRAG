<template>
  <div class="app-container">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <h1>DocAgentRAG</h1>
      </div>
      <div class="header-center">
        <div class="search-container">
          <input 
            type="text" 
            v-model="searchQuery" 
            placeholder="Enter search keywords..." 
            class="search-input"
            @keyup.enter="handleSearch"
          />
          <button 
            class="search-button" 
            @click="handleSearch"
            :disabled="isSearching"
          >
            {{ isSearching ? 'Searching...' : 'Search' }}
          </button>
        </div>
      </div>
      <div class="header-right">
        <button 
          class="classify-button" 
          @click="handleClassify"
          :disabled="isLoading"
        >
          {{ isLoading ? 'Classifying...' : 'One-click Classify' }}
        </button>
      </div>
    </header>

    <!-- Main Content -->
    <main class="app-main">
      <!-- Left Sidebar - Folder Structure -->
      <aside class="folder-sidebar">
        <h2>Document Structure</h2>
        <div class="folder-tree">
          <div class="folder-item">
            <div class="folder-name">doc</div>
            <div class="folder-children">
              <div class="subfolder-item">
                <div class="subfolder-name">Academic Materials</div>
                <div class="file-list">
                  <div class="file-item">paper1.pdf</div>
                  <div class="file-item">paper2.docx</div>
                </div>
              </div>
              <div class="subfolder-item">
                <div class="subfolder-name">Office Notices</div>
                <div class="file-list">
                  <div class="file-item">notice1.pdf</div>
                  <div class="file-item">notice2.docx</div>
                </div>
              </div>
              <div class="subfolder-item">
                <div class="subfolder-name">Reports</div>
                <div class="file-list">
                  <div class="file-item">report1.xlsx</div>
                  <div class="file-item">report2.xlsx</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- Right Content Area -->
      <section class="content-area">
        <h2>{{ isSearching ? 'Searching...' : (searchResults.length > 0 ? 'Search Results' : 'Welcome to DocAgentRAG System') }}</h2>
        
        <!-- Search Results -->
        <div class="search-results" v-if="searchResults.length > 0">
          <div class="result-item" v-for="(result, index) in searchResults" :key="index">
            <div class="result-header">
              <h3 class="result-filename">{{ result.filename }}</h3>
              <div class="result-score">
                <span class="score-label">Relevance:</span>
                <span class="score-value">{{ Math.round(result.score * 100) }}%</span>
              </div>
            </div>
            <div class="result-path">{{ result.path }}</div>
            <div class="result-snippet">{{ result.snippet }}</div>
          </div>
        </div>
        
        <!-- Empty State -->
        <div class="empty-state" v-if="searchResults.length === 0 && !isSearching && searchQuery">
          <p>No results found. Please try other keywords.</p>
        </div>
      </section>
    </main>

    <!-- Footer -->
    <footer class="app-footer">
      <p>DocAgentRAG System © 2026</p>
    </footer>
  </div>
</template>

<script>
export default {
  name: 'App',
  data() {
    return {
      isLoading: false,
      searchQuery: '',
      searchResults: [],
      isSearching: false
    }
  },
  methods: {
    handleClassify() {
      this.isLoading = true
      // Simulate API call
      setTimeout(() => {
        this.isLoading = false
        alert('Classification completed!')
      }, 2000)
    },
    handleSearch() {
      if (this.searchQuery.trim()) {
        this.isSearching = true
        // Simulate search results
        const mockResults = [
          {
            filename: 'paper1.pdf',
            path: 'doc/Academic Materials/paper1.pdf',
            score: 0.95,
            snippet: 'This is an academic paper about artificial intelligence, discussing the latest developments in deep learning...'
          },
          {
            filename: 'notice1.pdf',
            path: 'doc/Office Notices/notice1.pdf',
            score: 0.82,
            snippet: 'Notice about the artificial intelligence seminar, scheduled for next Monday...'
          },
          {
            filename: 'report1.xlsx',
            path: 'doc/Reports/report1.xlsx',
            score: 0.75,
            snippet: '2024 Q1 financial report, including income and expenditure data...'
          }
        ]
        // Simulate API call delay
        setTimeout(() => {
          this.searchResults = mockResults
          this.isSearching = false
        }, 1000)
      }
    }
  }
}
</script>

<style>
/* Global Reset */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

/* App Container */
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  background-color: #f5f5f5;
}

/* Header */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 2rem;
  background-color: #2c3e50;
  color: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.header-left h1 {
  font-size: 1.5rem;
  font-weight: 600;
}

.header-center {
  flex: 1;
  max-width: 600px;
  margin: 0 2rem;
}

.search-container {
  display: flex;
  width: 100%;
}

.search-input {
  flex: 1;
  padding: 0.75rem 1rem;
  border: none;
  border-radius: 4px 0 0 4px;
  font-size: 1rem;
  outline: none;
}

.search-button {
  padding: 0.75rem 1.5rem;
  background-color: #3498db;
  color: white;
  border: none;
  border-radius: 0 4px 4px 0;
  cursor: pointer;
  font-size: 1rem;
  transition: background-color 0.3s;
}

.search-button:hover {
  background-color: #2980b9;
}

.search-button:disabled {
  background-color: #95a5a6;
  cursor: not-allowed;
}

.header-right {
  display: flex;
  gap: 1rem;
}

.classify-button {
  padding: 0.75rem 1.5rem;
  background-color: #e74c3c;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
  transition: all 0.3s;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.classify-button:hover {
  background-color: #c0392b;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
}

.classify-button:disabled {
  background-color: #95a5a6;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

/* Main Content */
.app-main {
  display: flex;
  flex: 1;
  padding: 2rem;
  gap: 2rem;
}

/* Folder Sidebar */
.folder-sidebar {
  width: 300px;
  background-color: white;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow-y: auto;
}

.folder-sidebar h2 {
  font-size: 1.2rem;
  margin-bottom: 1.5rem;
  color: #333;
}

.folder-tree {
  font-size: 0.95rem;
}

.folder-item {
  margin-bottom: 1rem;
}

.folder-name {
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: #2c3e50;
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 4px;
  transition: background-color 0.3s;
}

.folder-name:hover {
  background-color: #f0f0f0;
}

.folder-children {
  margin-left: 1.5rem;
  margin-top: 0.5rem;
}

.subfolder-item {
  margin-bottom: 0.75rem;
}

.subfolder-name {
  font-weight: 500;
  margin-bottom: 0.5rem;
  color: #34495e;
  cursor: pointer;
  padding: 0.375rem;
  border-radius: 4px;
  transition: background-color 0.3s;
}

.subfolder-name:hover {
  background-color: #f0f0f0;
}

.file-list {
  margin-left: 1.5rem;
}

.file-item {
  padding: 0.375rem;
  color: #555;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.3s;
  margin-bottom: 0.25rem;
}

.file-item:hover {
  background-color: #f0f0f0;
}

/* Content Area */
.content-area {
  flex: 1;
  background-color: white;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow-y: auto;
}

.content-area h2 {
  font-size: 1.2rem;
  margin-bottom: 1.5rem;
  color: #333;
}

/* Search Results */
.search-results {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.result-item {
  padding: 1rem;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  transition: box-shadow 0.3s;
}

.result-item:hover {
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.result-filename {
  font-size: 1.1rem;
  font-weight: 600;
  color: #2c3e50;
}

.result-score {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.score-label {
  font-size: 0.875rem;
  color: #7f8c8d;
}

.score-value {
  font-size: 0.875rem;
  font-weight: 600;
  color: #3498db;
}

.result-path {
  font-size: 0.875rem;
  color: #7f8c8d;
  margin-bottom: 0.75rem;
}

.result-snippet {
  font-size: 0.95rem;
  color: #555;
  line-height: 1.4;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #7f8c8d;
}

/* Footer */
.app-footer {
  background-color: #2c3e50;
  color: white;
  padding: 1rem 2rem;
  text-align: center;
  font-size: 0.875rem;
}

/* Responsive Design */
@media (max-width: 768px) {
  .app-header {
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
  }

  .header-center {
    margin: 0;
    width: 100%;
  }

  .app-main {
    flex-direction: column;
    padding: 1rem;
    gap: 1rem;
  }

  .folder-sidebar {
    width: 100%;
    max-height: 300px;
  }
}
</style>
