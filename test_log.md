# AI Writer Lite 测试日志

## 已修复的 Bug 清单

| Bug ID | 问题 | 修复方案 | 状态 |
|--------|------|---------|------|
| #1 | 多素材识别缺失 | 添加正则匹配 `材料\s*\d+\s*[：:]` | ✅ |
| #2 | 缺少素材确认提示 | 添加 `print(f"已记录 {len(material_ids)} 条素材")` | ✅ |
| #3 | 草稿文件未自动打开 | 调用 `open_draft()` | ✅ |
| #4 | Windows 编码问题 | 移除 emoji 字符 | ✅ |
| #5 | 交互式架构与 skill 不兼容 | 实施方案 C：分步调用模式 | ✅ |
| #6 | 数据库字段名错误 | `ai_text` → `ai_original` | ✅ |
| #7 | 草稿文件路径重复 | `open_draft(draft_path)` → `open_draft(summary_id)` | ✅ |
| #8 | `system_prompts` 表缺失 | 在 `db.py` 添加表创建语句 | ✅ |
| #9 | 写作偏好萃取缺少自动触发 | 在定稿流程添加萃取检查 | ✅ |

---

## 核心架构

**分步调用模式**（skill 调用推荐）：
1. 收集信息：询问场景和目的
2. `save-materials` → 返回 material_ids
3. `generate` → 输出 prompt（含偏好注入）
4. AI 生成内容
5. `save-article` → 保存并打开草稿

**偏好萃取流程**：
1. `finalize` → 触发萃取检查
2. `distill-preference` → 输出萃取 prompt
3. AI 生成偏好总结
4. `save-preference` → 保存到 `system_prompts` 表

**偏好注入验证**：
- `get_scenario_prompt(scenario_type)` 使用 `prompt_type='scenario_{scenario_type}'`
- 场景偏好互不干扰
- 生成 prompt 时正确注入到 System 部分

---

## 最新测试记录

### [2026-03-31 12:36] 测试 #7 - 第一次使用者视角

**测试结果**：
- ✅ AI 正确执行"第 0 步：收集信息"（询问场景和目的）
- ✅ 分步调用流程完整可用（save-materials → generate → save-article）
- ✅ 场景偏好成功注入到生成 prompt
- ✅ 文章保存并自动打开草稿文件

**生成文章 ID**：`b14ec1f7`

---

## 系统状态

✅ 所有核心功能可用：
- 素材识别与保存
- 场景化写作
- 偏好萃取与注入
- 分步调用模式
- 草稿文件自动打开

✅ 偏好隔离机制正确：
- 场景偏好使用 `prompt_type='scenario_{type}'`
- 不同场景互不干扰
