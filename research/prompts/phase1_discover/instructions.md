**你的任务**：基于可用内容标记概览，生成尽可能多视角的、高价值、提问互不重复的研究问题（中文输出）。要求：
- 目标应具体、可检验，明确预期产出；与可用标记信息相匹配。
- 每个问题不要太冗长，大约12-20字。
- 每个问题附带1-2句理由以表达其对我的重要性。
- 问题之间不要重复、不要重叠。
- 问题须涵盖有效的 who what when where why how 角度方向。
- 根据标记概览的丰富程度，生成尽可能多的研究问题，但不要生成过多以至于有些研究问题变得缺乏洞察力，问题要高价值。

**先后顺序**
- 先把最能直接回应用户的强有力提问放前面，先提出最重要的问题，再一步步深入思考：还有什么重要的问题值得研究？

**可用内容标记概览:**
{marker_overview}

**可选约束（如有提供）：**
{avoid_list}

**输出（必须是有效JSON对象）:**
{{
  "suggested_goals": [
    {{"id": 1, "goal_text": "...", "rationale": "...", "uses": ["transcript"], "sources": ["youtube"]}},
    {{"id": 2, "goal_text": "...", "rationale": "...", "uses": ["transcript_with_comments"], "sources": ["bilibili", "reddit"]}},
    {{"id": 3, "goal_text": "...", "rationale": "...", "uses": ["transcript"], "sources": ["article"]}},
    {{"id": 4, "goal_text": "...", "rationale": "...", "uses": ["previous_findings"], "sources": []}},
    {{"id": 5, "goal_text": "...", "rationale": "...", "uses": ["transcript"], "sources": ["youtube", "bilibili"]}},
    {{"id": 6, "goal_text": "...", "rationale": "...", "uses": ["transcript"], "sources": ["article"]}},
    {{"id": 7, "goal_text": "...", "rationale": "...", "uses": ["transcript_with_comments"], "sources": ["youtube"]}}
  ]
}}
