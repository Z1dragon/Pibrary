# 📚 Pibrary——你的中文 RAG 个人知识图书馆

基于 **LangChain + Milvus + 智谱 GLM** 的工业级中文 RAG 问答系统。支持多格式文档自动加载、向量化检索、两阶段精排、防幻觉问答与来源溯源。

## 📋 功能特性

- **全格式文档支持**：PDF / Markdown / TXT / EPUB / MOBI 自动解析
- **工业级向量检索**：基于 Milvus 2.3+ 向量数据库，高效稳定
- **两阶段检索架构**：向量召回 + BGE Reranker 重排序精排
- **防幻觉问答**：Prompt 层面严格约束，回答必须基于检索文档
- **来源溯源**：回答附带文档来源、页码/章节、片段编号
- **增量构建**：文件级哈希校验，避免重复向量化
- **可视化界面**：React + Vite + FastAPI，上传/构建/问答一站式操作

## 🏗️ 技术栈

| 组件 | 技术选型 |
|------|---------|
| 核心框架 | LangChain |
| 向量数据库 | Milvus 2.3+ (Standalone) |
| Embedding 模型 | BAAI/bge-small-zh-v1.5 |
| 重排序模型 | BAAI/bge-reranker-base |
| 大语言模型 | 智谱 AI GLM-4 (兼容 OpenAI 接口) |
| Web 前后端 | React(Vite) + FastAPI |
| 配置管理 | python-dotenv |

## 📁 项目结构

```
my_rag_kb/
├── .env.example                # 环境变量模板
├── .gitignore                  # Git 忽略配置
├── requirements.txt            # Python 依赖
├── README.md                   # 本文档
├── config.py                   # 全局配置（读取 .env）
├── data/
│   ├── raw/                    # 原始文档存放目录
│   └── processed/              # 处理元数据（增量校验用）
├── docker/
│   └── docker-compose.yml      # Milvus 一键部署
└── src/
    ├── __init__.py
    ├── data_loader.py          # 文档加载（多格式解析）
    ├── text_splitter.py        # 文档切分（中文优化）
    ├── indexer.py              # 向量化与索引（Milvus）
    ├── retriever.py            # 两阶段检索（召回+重排序）
    ├── rag_chain.py            # RAG 问答链（GLM + 防幻觉）
    ├── app.py                  # FastAPI Web 入口
    └── static/
      └── dist/               # Vite 构建产物（FastAPI 直接托管）
frontend/
├── package.json              # 前端依赖与脚本
├── vite.config.js            # Vite 配置（输出到 src/static/dist）
└── src/
    ├── App.jsx               # React 页面逻辑
    ├── main.jsx              # React 入口
    └── styles.css            # 页面样式
```

## 🚀 快速开始

### 1. 环境准备

**系统要求**：
- Python 3.10+
- Docker & Docker Compose（用于运行 Milvus）
- 8GB+ 可用内存（Milvus + Embedding 模型加载）

### 2. 安装依赖

```bash
# 克隆/进入项目目录
cd my_rag_kb

# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 安装前端依赖（首次）
cd frontend
npm install
cd ..
```

### 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填写你的智谱 AI API Key
# 在 https://open.bigmodel.cn/ 注册获取
```

`.env` 最小配置示例：

```env
GLM_API_KEY=your_actual_api_key_here
GLM_MODEL_NAME=glm-4
MILVUS_HOST=localhost
MILVUS_PORT=19530
```

### 4. 启动 Milvus 向量数据库

确保你当前位于项目根目录 `my_rag_kb/` 中：

```bash
# 1. 确保在 my_rag_kb 目录下
cd /Users/Zhuanz1/Documents/AI_Study/MindOS/personal_MindOS/my_rag_kb

# 2. 进入 docker 目录
cd docker

# 3. 启动 Milvus（包含 etcd + MinIO + Milvus Standalone）
# 请确保 Docker Desktop 已经启动！
docker-compose up -d

# 4. 确认服务状态
docker-compose ps
```

验证 Milvus 是否就绪：

```bash
curl http://localhost:9091/healthz
# 返回 "OK" 表示服务正常
```

### 5. 启动 Web 应用

```bash
# 先构建前端静态资源（修改前端后需重新执行）
cd frontend
npm run build
cd ..

# 启动 FastAPI
uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

浏览器访问 `http://localhost:8000`，即可开始使用。

## 📖 使用指南

### 上传文档构建知识库

1. 在左侧边栏点击「上传文档」区域
2. 选择本地 PDF / Markdown / TXT / EPUB / MOBI 文件（支持多选）
3. 点击「📥 构建知识库」按钮
4. 等待文档解析、切分、向量化完成
5. 左侧「知识库状态」区域显示已索引文档列表

### 知识库问答

1. 在底部输入框输入问题
2. 系统自动检索知识库中最相关的文档片段
3. 基于检索结果生成回答（防幻觉机制）
4. 展开「📖 查看参考来源」可查看引用文档详情

### 调整检索参数

- **启用重排序**：开启后使用 BGE Reranker 对召回结果精排，提升准确性
- **向量召回数量**：第一阶段从 Milvus 召回的候选文档数
- **最终返回文档数**：经重排序后送入 LLM 的文档数量

## ⚙️ 智谱 AI GLM API 配置说明

本项目使用智谱 AI GLM 系列模型，兼容 OpenAI 接口规范。

1. 访问 [智谱 AI 开放平台](https://open.bigmodel.cn/) 注册账号
2. 在控制台创建 API Key
3. 将 API Key 填入 `.env` 文件的 `GLM_API_KEY` 字段

支持的模型（通过 `GLM_MODEL_NAME` 切换）：

| 模型名 | 说明 |
|--------|------|
| `glm-4` | 旗舰模型，能力最强 |
| `glm-4-flash` | 快速模型，性价比高 |
| `glm-4-long` | 长上下文模型，支持 128K |

### 切换其他 OpenAI 兼容模型

由于采用 OpenAI 兼容接口，可轻松切换到其他提供商：

```env
# 示例：切换为 DeepSeek
GLM_API_KEY=your_deepseek_key
GLM_API_BASE=https://api.deepseek.com
GLM_MODEL_NAME=deepseek-chat
```

## 🔧 高级配置

### 文档切分参数

```env
# 切片大小（字符数），建议 300-800
CHUNK_SIZE=500
# 切片重叠，建议为切片大小的 15-25%
CHUNK_OVERLAP=100
```

### Milvus 认证（生产环境）

```env
MILVUS_USER=your_username
MILVUS_PASSWORD=your_password
```

### GPU 加速 Embedding

```env
# NVIDIA GPU
EMBEDDING_DEVICE=cuda
# Apple Silicon
EMBEDDING_DEVICE=mps
```

## 🧪 测试与回归

项目已内置 **API smoke 回归测试**，覆盖以下接口分组：

- `chat`：`/api/chat`
- `history`：`/api/chat/history`
- `build`：`/api/kb/build`
- `upload`：`/api/notes/upload`
- `delete`：`/api/kb/file`、`/api/notes`

测试目录结构：

```text
tests/
├── conftest.py
├── test_chat_api.py
├── test_history_api.py
├── test_build_api.py
├── test_upload_api.py
└── test_delete_api.py
```

### 1. 安装测试依赖

```bash
pip install -r requirements-dev.txt
```

> 若你的本机出现 SSL 证书报错（如 `CERTIFICATE_VERIFY_FAILED`），可临时使用：

```bash
pip install -r requirements-dev.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

### 2. 运行全部测试

```bash
.venv/bin/python -m pytest -q
```

### 3. 按模块定向回归（推荐日常开发）

```bash
# 只测聊天相关
.venv/bin/python -m pytest -q tests/test_chat_api.py

# 只测历史相关
.venv/bin/python -m pytest -q tests/test_history_api.py

# 只测构建/上传/删除
.venv/bin/python -m pytest -q tests/test_build_api.py tests/test_upload_api.py tests/test_delete_api.py
```

## 🤖 CI 持续集成

项目已配置 GitHub Actions 工作流：`.github/workflows/ci.yml`

- **backend job**：语法检查（`compileall`）+ `pytest`
- **frontend job**：`npm ci` + `npm run build`

触发时机：

- `push`
- `pull_request`

建议：所有功能改动先本地执行 `pytest -q`，再发起 PR，让 CI 做最终门禁。

## 🛠️ 常见问题

**Q: Milvus 启动失败？**
- 确认 Docker 已安装且正在运行
- 确认端口 19530、9091、9000、9001 未被占用
- 执行 `docker-compose logs milvus` 查看日志

**Q: Embedding 模型下载慢？**
- 模型首次运行时从 HuggingFace 下载，可设置镜像：
  ```bash
  export HF_ENDPOINT=https://hf-mirror.com
  ```

**Q: 回答质量不佳？**
- 调大 `RETRIEVER_TOP_K` 增加召回候选
- 启用重排序（Reranker）
- 调小 `CHUNK_SIZE` 提高切片粒度
- 降低 `GLM_TEMPERATURE`（如设为 0.05）

## 📄 许可证

MIT License
