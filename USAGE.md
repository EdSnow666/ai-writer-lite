# AI Writer Lite - 使用指南

## 已完成功能 ✅

### P0 核心功能（已实现）
- ✅ 数据库初始化（SQLite + WAL 模式）
- ✅ 智能素材识别（文本/文件/JSON）
- ✅ 临时文件管理（自动清理 24 小时）
- ✅ 三粒度 Diff 计算（段落/句子/词级）
- ✅ AI 生成（带引用和偏好）
- ✅ 编辑记录管理
- ✅ 偏好萃取（3条或10条触发）

### 测试结果
```
=== 测试初始化 ===
✓ 数据库初始化成功
⚠ jieba 未安装（可选）

=== 测试素材导入 ===
✓ 短文本识别正确
✓ 长文本导入成功: mat-c396f79f

=== 测试 Diff 计算 ===
✓ 段落 Diff: 1 处修改
✓ 句子 Diff: 1 处修改

✅ 所有测试通过
```

## 文件结构

```
ai-writer-lite/
├── SKILL.md              # Skill 定义
├── README.md             # 项目说明
├── USAGE.md              # 本文件
├── requirements.txt      # 依赖列表
├── test.py              # 测试脚本
├── main.py              # 主入口（待完善）
├── core/                # 核心模块
│   ├── db.py                 # 数据库管理
│   ├── input_parser.py       # 输入识别
│   ├── generator.py          # AI 生成
│   ├── diff_engine.py        # Diff 计算
│   ├── distiller.py          # 偏好萃取
│   ├── temp_manager.py       # 临时文件
│   └── edit_records.py       # 编辑记录
├── data/
│   └── writer.db        # SQLite 数据库
└── temp/                # 临时草稿
```

## 数据库表

| 表名 | 说明 |
|------|------|
| materials | 素材库 |
| summaries | AI 摘要 |
| edit_records | 编辑记录（含三粒度 diff）|
| writing_preferences | 写作偏好模型 |

## 下一步开发（P1/P2）

### P1 - 自动化功能
- [ ] 完善 main.py 主入口
- [ ] 实现完整的对话流程
- [ ] 集成到 Claude Code skill 系统

### P2 - 监控优化
- [ ] 工作流日志记录
- [ ] 优化建议生成
- [ ] 多偏好模型切换

## 快速测试

```bash
cd ~/.claude/skills/ai-writer-lite
python test.py
```

## 依赖安装

```bash
# 必需
pip install anthropic

# 可选（更好的中文分词）
pip install jieba
```

## 环境变量

```bash
# 可选：配置后启用自动偏好萃取
export ANTHROPIC_API_KEY="your-api-key"
```
