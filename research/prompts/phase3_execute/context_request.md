**你的任务**：为帮助你更好的回答 "{goal}" 这个问题，告诉我你需要的额外上下文请求。

**可请求的上下文**：
- 标记概览：
{marker_overview}
- 已检索内容：
{retrieved_content}
- 先前分析摘要：
{scratchpad_summary}
- 已处理数据块：
{previous_chunks_context}

**请求格式**：
- 使用 `request_type: "full_content_item"` 请求完整内容
- 使用 `request_type: "by_marker"` 请求特定标记的上下文
- 使用 `request_type: "semantic"` 请求语义检索

**输出要求**：
- `step_id`: 步骤ID（整数）
- `requests`: 数组（如果需要更多上下文）或空数组 `[]`（如果信息充足）
- `insights`: 简要说明需要/不需要更多上下文的原因（可选）
- `confidence`: 对当前上下文充足性的信心（0.0-1.0，可选）

**语言要求**：
- 所有输出必须使用中文
- 专业术语需提供跨语言引用（格式：中文术语（原文））

**示例输出（需要更多上下文）**：
{{
  "step_id": {step_id},
  "requests": [
    {{
      "id": "req_1",
      "request_type": "full_content_item",
      "source_link_id": "link_id_1",
      "content_types": ["transcript"],
      "reason": "需要完整转录以分析具体细节",
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
  "insights": "需要更多上下文才能完成分析",
  "confidence": 0.3
}}

**示例输出（上下文充足）**：
{{
  "step_id": {step_id},
  "requests": [],
  "insights": "已有足够上下文",
  "confidence": 0.8
}}

