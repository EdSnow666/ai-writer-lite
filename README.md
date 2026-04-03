# AI Writer Lite

轻量级 AI 写作助手，支持素材管理、智能生成、修改追踪和偏好学习。

## 核心功能

### 自定义 Prompt（新）
每个写作场景可存储用户自定义的 prompt，三层注入顺序：
1. 底层硬编码：`你是一个专业的写作助手。`
2. 用户自定义 prompt（如果有）
3. 萃取偏好（场景偏好、写作偏好、定稿特征）

### AI 模型署名（新）
生成的内容末尾自动标注模型名称，并存储到数据库：
```
> 本文由 Claude Opus 4.6 生成
```

### 场景化写作

| 场景 | 说明 |
|------|------|
| academic | 学术论文（严谨论证，注重引用）|
| daily_note | 日常笔记（简洁明了）|
| social_media | 社交媒体（吸引力强）|
| report | 工作报告（结构清晰）|
| creative | 创意写作（文采丰富）|
| objective | 客观描述（中立记录）|

### 两阶段写作流程

**第一阶段（编辑记录）**：用户修改 → AI 分析编辑比例（阈值 30%）→ 保存到 `edit_records`

**第二阶段（打磨轮次，可选）**：用户输入"打磨" → AI 提出建议 → 用户在编辑器修改 → 同步到 `revision_rounds`

**定稿**：用户输入"定稿" → 标记 `is_final=1` → 保存到 `final_versions`

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行交互模式

```bash
python main.py
```

### 3. 命令行调用

```bash
# 保存素材
python main.py 'save-materials <素材内容>'

# 生成文章
python main.py 'generate {"material_ids":["mat-xxx"],"scenario":"academic","purpose":"论证观点","intent":"写文章"}'

# 保存文章
python main.py 'save-article {"scenario":"academic","purpose":"阐述观点","content":"文章内容"}'

# 列出文章
python main.py list

# 打磨文章
python main.py "polish <article_id>"
```

## 数据库结构

| 表名 | 用途 |
|------|------|
| `materials` | 素材库（含 book_title, tags, page_number 等结构化字段）|
| `summaries` | 写作摘要（含 scenario_type、writing_purpose、ai_model）|
| `edit_records` | 用户修改记录（AI 原文 → 用户修改稿），含 `is_final` |
| `revision_rounds` | 打磨轮次记录（AI 建议、用户修改稿、是否响应）|
| `final_versions` | 用户定稿表（清理后的最终稿）|
| `scenario_preferences` | 场景化偏好模型 |
| `user_custom_prompts` | 用户自定义 Prompt（按场景存储，支持历史版本）|

## 萃取类型

| 类型 | 触发条件 | 用途 |
|------|----------|------|
| 写作偏好 | 3/10 条编辑记录 | 基础写作风格 |
| 定稿特征 | 10 篇定稿 | 初稿质量优化 |
| 场景偏好 | 3/10 条编辑记录（按场景）| 场景化写作风格 |

## 文件结构

```
ai-writer-lite/
├── skill.md           # Skill 描述（Claude Code 调用）
├── README.md          # 本文件
├── requirements.txt   # 依赖
├── main.py            # 主入口
├── config.py          # 配置
├── core/
│   ├── db.py                # 数据库
│   ├── generator.py         # Prompt 构建
│   ├── input_parser.py      # 输入识别
│   ├── distiller.py         # 偏好萃取
│   ├── feedback_distiller.py # 用户反馈萃取
│   ├── temp_manager.py      # 临时文件
│   ├── edit_records.py      # 编辑记录
│   └── revision_manager.py  # 打磨轮次管理
├── data/
│   └── writer.db           # SQLite 数据库
└── drafts/                 # 草稿文件
```

## 打磨建议格式

**注入格式**：`%%（问题：XX，建议：XX，用户反馈：）%%`

- 建议注入到对应段落后
- 用户可在编辑器中修改文本，或在 `用户反馈：` 后填写想法
- 定稿时 `%%...%%` 内容自动移除

## 注意事项

- jieba 可选：未安装时词级 Diff 使用空格分词
- 临时文件每次启动时自动清理 24 小时前的草稿
- 使用 WAL 模式防止并发锁定

## 更新日志

### v1.0.0 (2026-04-03)
- 新增自定义 Prompt 功能（按场景存储）
- 新增 AI 模型署名功能
- 新增三层 Prompt 注入机制
- 优化场景化写作流程
- 完善两阶段写作工作流