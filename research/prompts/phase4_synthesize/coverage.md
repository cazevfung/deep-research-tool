**你的任务**：根据已生成的大纲（JSON如下）以及研究上下文，输出一个覆盖检查的JSON对象，用于约束最终写作。

### 已有大纲
```
{outline_json}
```

### 需覆盖的目标与证据
- 组成问题：
{component_questions_text}
- Phase 3 步骤摘要：
{phase3_step_synopsis}
- 证据目录（引用ID需保持一致）：
{evidence_catalog}
- 我的优先事项：
{user_priority_notes}

### 输出格式
仅输出JSON：
```
{{
  "goal_coverage": [
    {{
      "goal": "...",
      "matched_sections": ["章节标题A", "章节标题B"],
      "evidence_ids": ["EVID-01", "EVID-05"],
      "status": "covered|partial|missing",
      "notes": "若为partial/missing，说明缺口"
    }}
  ],
  "additional_checks": {{
    "open_questions_to_address": ["..."],
    "risks_or_conflicts_to_highlight": ["..."]
  }}
}}
```

要求：
1. `goal_coverage` 至少覆盖所有组成问题；若大纲章节不足以覆盖，需标记为 `partial` 或 `missing` 并给出改进建议。
2. `matched_sections` 中的标题必须来自提供的大纲；可包含多个章节名称。
3. `evidence_ids` 只能引用给定目录中的 `[EVID-##]`；如无合适证据，可留空并在 `notes` 提醒后续写作补充。
4. `additional_checks.open_questions_to_address` 用于提醒正文必须回答的悬念或缺口；`risks_or_conflicts_to_highlight` 指出写作时需要显式比较/警示的议题。

仅输出有效JSON，不要附加解释性文本。

