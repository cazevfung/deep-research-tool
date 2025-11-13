**你的任务**：围绕步骤的提问 "{goal}" 撰写详细答案解答问题。
- 在结构化报告中于"重要发现"与"深入分析"之间插入一篇完整文章，并写入 `findings.article` 字段。
- 文章可以提取检索内容中的观点和论证，进行深度分析、同意、质疑与综合。
- 运用你的专业知识、推理能力和领域理解，提供对问题的直接答案和洞察，而非简单复述或总结检索到的信息点。
- 提炼 who, what, when, how，不直接列出这些w，但在文章中体现相关信息。
- 文章应自然衔接上下文，合理引用证据、推理链与我的优先事项，保持专业、克制的语气。

**上下文（简要）**
{scratchpad_summary}
{previous_chunks_context}

**严禁重复以下内容，杜绝复述这些已知观点信息**
{cumulative_digest}

**相关内容的标记概览**
{marker_overview}

**已检索的完整内容**
{retrieved_content}

**语言要求（重要）:**
- **所有输出必须使用中文**：无论源内容使用何种语言（英语、日语、韩语等），所有分析结果、摘要、洞察、论点、证据描述等都必须用中文表述。
- **跨语言术语引用**：当遇到专业术语、专有名词、品牌名称或关键概念时：
  - 优先使用中文表述，并在首次出现时提供原文（括号标注）
  - 对于没有标准中文翻译的术语，使用中文音译或描述性翻译，并附原文
- **引用原文的处理**：
  - 在`quote`字段中，如果原文是外文，保留原文并添加中文翻译
  - 格式：`"原文内容（中文翻译）"` 或 `"中文翻译[原文: Original Text]"`
  - 在`supporting_evidence`、`description`等字段中，优先使用中文，必要时提供原文对照
- **一致性**：确保整个输出中同一术语的中文表述保持一致

**内容检索与使用:**
- 标记概览显示了可用内容中的关键信息点，用于快速判断内容相关性。
- 若信息充足则直接分析，否则先请求补充内容。
- 如需更多上下文，可在 `requests` 字段中请求：完整内容项（指定 link_id 和内容类型）、基于标记检索、按话题检索，或语义向量检索（`request_type: "semantic"`，提供 query，可指定 `source_link_ids` 或 `chunk_types`）。

**重要：findings 字段的条件性要求:**
- **当 `requests` 数组包含任何请求项时**：`findings` 必须为 `null` 或完全省略，不要提供任何发现内容。此时只需提供 `requests`、`insights` 和 `confidence`。
- **当 `requests` 数组为空或不存在时**：必须提供完整的 `findings` 对象（包括 `summary`、`article` 等所有必需字段）。
- 这样可以避免在请求更多上下文时重复生成发现内容，提高处理效率。只有在获得所有必要信息后，才应提供完整的分析结果。

**输出（必须是有效JSON）**

**示例1：当需要更多上下文时（findings 应为 null）:**
{{
  "step_id": 1,
  "requests": [
    {{
      "id": "req_1",
      "request_type": "full_content_item",
      "source_link_id": "link_id_1",
      "content_types": ["transcript", "comments"],
      "reason": "需要完整内容以深入分析标记 'FACT: X' 的相关证据链",
      "priority": "high"
    }},
    {{
      "id": "req_2",
      "request_type": "by_marker",
      "marker_text": "FACT: 玩家留存率在赛季重置后下降了30%",
      "source_link_id": "link_id_1",
      "content_type": "transcript",
      "context_window": 2000,
      "reason": "需要该事实标记的完整上下文以了解细节"
    }}
  ],
  "findings": null,
  "insights": "需要更多上下文才能完成分析",
  "confidence": 0.3
}}

**示例2：当信息充足时（提供完整的 findings）:**
{{
  "step_id": 1,
  "requests": [],
  "findings": {{
    "summary": "本步骤的核心发现（避免重复，聚焦结论+关键证据）。所有输出必须使用中文，即使源内容为其他语言。",
    "article": "完整文章：综合运用检索证据与专业知识，直接回答步骤目标问题，提供基于证据和推理的完整答案，而非仅总结检索内容。先概览后深入，结合证据与推理构建完整论证链条。",
    "points_of_interest": {{
      "key_claims": [{{"claim": "核心论点（中文表述，必要时附原文）", "supporting_evidence": "支持证据（中文，原文引用需标注）"}}],
      "notable_evidence": [{{"evidence_type": "quote|data|example", "description": "证据描述（中文）", "quote": "原文引用（如需，格式：原文（中文翻译））"}}],
      "controversial_topics": [{{"topic": "争议话题（中文）", "opposing_views": ["观点1（中文）", "观点2（中文）"], "intensity": "high|medium|low"}}],
      "surprising_insights": ["意外洞察（中文表述）"],
      "specific_examples": [{{"example": "具体例子（中文，术语附原文）", "context": "上下文说明（中文）"}}],
      "open_questions": ["开放问题（中文）"]
    }},
    "analysis_details": {{
      "five_whys": [
        {{"level": 1, "question": "为什么会出现X现象？（中文）", "answer": "因为Y原因...（中文）"}},
        {{"level": 2, "question": "为什么会有Y原因？（中文）", "answer": "因为Z根本原因...（中文）"}},
        {{"level": 3, "question": "为什么...？（中文）", "answer": "因为...（中文）"}},
        {{"level": 4, "question": "为什么...？（中文）", "answer": "因为...（中文）"}},
        {{"level": 5, "question": "为什么...？（中文）", "answer": "因为...（中文）"}}
      ],
      "assumptions": ["假设1（中文）", "假设2（中文）"],
      "uncertainties": ["不确定性1（中文）", "不确定性2（中文）"]
    }}
  }},
  "insights": "关键洞察（一句话要点，必须使用中文）",
  "confidence": 0.0
}}

