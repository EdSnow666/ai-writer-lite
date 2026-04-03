---
name: ai-writer-lite
working_directory: C:\Users\Edward Snow\.claude\skills\ai-writer-lite
description: |
  独立的 AI 写作助手。自动识别素材、生成带引用的文本、追踪修改习惯、自动学习写作偏好。
  支持动态修改：用户可修改任意段落，AI 分析偏好并重写；多轮修改记录用于萃取优化。
  支持场景化写作：引导用户选择写作场景（学术/日常/社交媒体/报告/创意/客观），分场景学习偏好。

  **重要：所有命令必须在此目录下执行：C:\Users\Edward Snow\.claude\skills\ai-writer-lite**

  **架构说明（AI 必读）**：
  - Python 程序负责：素材管理、数据库操作、prompt 构建、文件操作
  - 外部 AI（你）负责：内容生成、打磨建议生成
  - 工作流程：用户请求 → Python 保存素材到数据库 → Python 构建 prompt → AI 生成内容 → Python 保存结果 → Python 打开草稿文件

  **AI 使用说明（重要）：**

  **第 0 步：收集信息（强制）**
  - 询问用户选择写作场景（6 种：academic/daily_note/social_media/report/creative/objective）
  - 询问用户写作目的（如"阐述观点"、"记录想法"等）
  - **【新增】询问自定义 Prompt**：显示当前场景已保存的自定义 prompt，询问是否修改/创建

  **第 1 步：保存素材**
  `python main.py 'save-materials <用户原始素材>'`
  - 返回：`[MATERIAL_IDS] mat-xxx,mat-yyy,mat-zzz`
  - **⚠️ 警告：必须原封不动使用用户提供的素材格式，禁止擅自转换格式！**

  **第 2 步：生成文章**
  `python main.py 'generate {"material_ids":["mat-xxx"],"scenario":"academic","purpose":"论证观点","intent":"写文章"}'`
  - 输出 prompt，AI 根据 prompt 生成内容
  - **重要**：生成后立即调用 `save-article`，不要先展示给用户确认
  - **【新增】文章末尾必须署名**：`> 本文由 [模型名称] 生成`

  **第 3 步：保存并打开草稿**
  `python main.py 'save-article {"material_ids":["mat-xxx"],"scenario":"academic","purpose":"论证观点","content":"AI生成的完整文章内容"}'`
  - 返回：`[SUMMARY_ID] xxx`、`[DRAFT_PATH] xxx`、`[AI_MODEL] xxx`
  - 自动打开草稿文件供用户手动修改

  **第 4 步：用户修改后同步**
  - 用户修改草稿后告诉 AI「已修改」或「同步」
  - AI 调用：`python main.py 'sync <summary_id>'`
  - 编辑比例 ≥30%：保存到 `edit_records` 表，用于学习写作偏好

  **其他命令**：
  - 列出文章：`python main.py list`
  - 查看文章：`python main.py "resume <article_id>"`
  - 打磨文章：`python main.py "polish <article_id>"`（AI 只提建议，不重写）

  **禁止操作**：
  - 不要直接查询数据库
  - 不要在 polish 后帮用户重写文章
  - **不要擅自修改用户提供的素材格式**

  触发场景：
  - 用户说"写一篇文章" / "新建文章" / 提供素材和写作需求
  - 用户说"打磨 XX 文章"
---

# AI 写作助手 Lite

## ⚠️ 素材格式警告（必读）

**用户提供的素材格式必须原封不动传递给 `save-materials` 命令！**

| 用户原始格式（正确） | AI 擅自转换的格式（错误） |
|---|---|
| `## 1. 笔记_XXXXX` | `材料1：【书名】xxx` |
| `**书名**: xxx \| **页码**: 3` | `【书名】xxx【高亮】xxx` |

**后果**：擅自转换格式会导致 `book_title`、`tags`、`page_number` 等结构化字段全部为 None。

## 核心功能

### 1. 自定义 Prompt（新功能）

每个写作场景可存储一个用户自定义的 prompt，三层注入顺序：
1. 底层硬编码：`你是一个专业的写作助手。`
2. 用户自定义 prompt（如果有）
3. 萃取偏好（场景偏好、写作偏好、定稿特征）

**交互流程**：
```
【自定义 Prompt 设置】
当前场景：学术论文
当前自定义 Prompt：
────────────────────
{显示内容}
────────────────────
是否修改？(修改/不修改)

[如果没有设置]
当前场景未设置自定义 Prompt。是否创建？(创建/不创建)
```

### 2. AI 模型署名（新功能）

生成的内容末尾需标注模型名称，格式：
```
> 本文由 Claude Opus 4.6 生成
```

模型名称自动提取并存储到 `summaries.ai_model` 字段。

### 3. 两阶段写作流程

**第一阶段（编辑记录）**：用户修改 → AI 分析编辑比例（阈值 30%）→ 保存到 `edit_records`

**第二阶段（打磨轮次，可选）**：用户输入"打磨" → AI 提出建议 → 用户在编辑器修改 → 同步到 `revision_rounds`

**定稿**：用户输入"定稿" → 标记 `is_final=1` → 保存到 `final_versions`

### 4. 场景化写作

| 场景 | 说明 |
|------|------|
| academic | 学术论文（严谨论证，注重引用）|
| daily_note | 日常笔记（简洁明了）|
| social_media | 社交媒体（吸引力强）|
| report | 工作报告（结构清晰）|
| creative | 创意写作（文采丰富）|
| objective | 客观描述（中立记录）|

## 数据库结构

| 表名 | 用途 |
|------|------|
| `materials` | 素材库（含 book_title, tags, page_number 等结构化字段）|
| `summaries` | 写作摘要（含 scenario_type、writing_purpose、**ai_model**）|
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

## 命令

| 命令 | 说明 |
|------|------|
| `quit` / `exit` | 退出 |
| `定稿` / `完成` | 结束当前写作会话 |
| `打磨` / `polish` | AI 提出修改建议，打开草稿文件供编辑 |
| `重生成` | AI 基于用户修改完全重写 |
| `sync` / `同步` | 将草稿文件修改同步到数据库 |

## 打磨建议格式

**注入格式**：`%%（问题：XX，建议：XX，用户反馈：）%%`

- 建议注入到对应段落后
- 用户可在编辑器中修改文本，或在 `用户反馈：` 后填写想法
- 定稿时 `%%...%%` 内容自动移除

## 测试规则

1. **不要擅自改代码** - 先跑完完整测试流程，等用户确认后再改
2. **禁止模拟执行** - 必须实际调用 Python 程序
3. **全过程日志记录** - 测试前先读取 `test_log.md`
4. **双重视角测试** - 以"第一次使用者"视角执行，再启用元监控评估
