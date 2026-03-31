# AI Writer Lite

轻量级 AI 写作助手，支持素材管理、智能生成、修改追踪和偏好学习。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key（可选）

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

未配置时仍可使用所有功能，但会跳过自动偏好萃取。

### 3. 运行测试

```bash
python test.py
```

## 功能特性

- ✅ 智能素材识别（文本/文件/JSON）
- ✅ AI 生成带引用的文本
- ✅ 三粒度 Diff 追踪（段落/句子/词级）
- ✅ 自动偏好萃取（3条或10条触发）
- ✅ 临时文件自动清理（24小时）
- ✅ WAL 模式防并发锁定

## 文件结构

```
ai-writer-lite/
├── SKILL.md           # Skill 描述
├── README.md          # 本文件
├── requirements.txt   # 依赖
├── test.py           # 测试脚本
├── main.py           # 主入口（待完善）
├── core/
│   ├── db.py                # 数据库
│   ├── input_parser.py      # 输入识别
│   ├── generator.py         # AI 生成
│   ├── diff_engine.py       # Diff 计算
│   ├── distiller.py         # 偏好萃取
│   ├── temp_manager.py      # 临时文件
│   └── edit_records.py      # 编辑记录
├── data/
│   └── writer.db           # SQLite 数据库
└── temp/                   # 临时草稿
```

## 使用示例

通过 Claude Code 调用 skill：

```
用户: "帮我写一段关于 AI 的文本"
AI: 触发 ai-writer-lite skill
```

## 注意事项

- jieba 可选：未安装时词级 Diff 使用空格分词
- API Key 可选：未配置时跳过自动萃取
- 临时文件每次启动时自动清理 24 小时前的草稿
