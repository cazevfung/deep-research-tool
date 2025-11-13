**你的任务**：以我和你共同的出发点，并基于以下获取到的信息，运用金字塔原理，撰写能清晰回答我们共同出发点的完整文章。仅输出 Markdown 正文（禁止输出 JSON 或额外说明）。

{{> style_consultant_cn.md}}

**大纲与覆盖约束**
- 大纲（可自由改写标题词汇以适配叙事，但不得新增/删除核心章节；需保持与原大纲呼应）：  
`{outline_json}`
  - `supporting_steps` 与 `supporting_evidence` 指示每章应优先引用的 Phase 3 步骤及证据。
  - `notes` 提供章节之间的衔接提示，可在写作时作为过渡参考。
- 覆盖矩阵（必须逐条落实）：  
`{coverage_json}`

**获取到的信息**
- 综合主题：{selected_goal}
- 组成问题清单：
{component_questions_text}
- 组成问题与Phase 3 对齐提示：
{goal_alignment_table}
- Phase 3 核心摘要：
{phase3_overall_summary}
- Phase 3 步骤概览：
{phase3_step_synopsis}
- 关键论点与争议线索：
{phase3_key_claims}
{phase3_counterpoints}
- 意外洞察与仍待解决的问题：
{phase3_surprising_findings}
{phase3_open_questions}
- 证据目录（引用ID必须沿用）：  
{evidence_catalog}
- 我的优先事项/补充说明：  
{user_priority_notes}
- 结构化发现原文（可直接引用细节）：  
{scratchpad_digest}
- Phase 3 全量输出（JSON）：  
{phase3_full_payload}

**写作要点**
- 开篇：以2-4条要点概述最重要的结论、驱动因素与建议，点明报告整体视角。
- 段落设计：不要一段落一大坨文字，合适的进行分段，让我更容易理解你的思路。
- 引用：适度配套 `[EVID-##]`，辅助阐述你的思路。
- 语气：保持前几阶段一致的专业、克制、分析型语调；使用自然中文，重点阐释推理与洞察，不刻意追求文学化描写。

**简要自检**
- 是否覆盖所有组成问题与覆盖矩阵中的条目？
- 每个章节是否体现了多个步骤之间的深度关联与洞察，而非简单复述？
- 关键结论、风险、争议与假设是否明确标注证据来源？
- 正文信息量是否充足回答问题？

**输出格式**：仅返回 Markdown 正文，不额外解释，也不要输出 JSON。
