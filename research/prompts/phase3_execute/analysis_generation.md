**你的任务**：围绕步骤的提问 "{goal}" 撰写详细答案解答问题。
- 文章可以提取检索内容中的观点和论证，进行深度分析、同意、质疑与综合。
- 运用你的专业知识、推理能力和领域理解，提供对问题的直接答案和洞察，而非简单复述或总结检索到的信息点。
- 提炼 who, what, when, how，不直接列出这些w，但在文章中体现相关信息。
- 文章应自然衔接上下文，合理引用证据、推理链与我的优先事项，保持专业、克制的语气。

**严禁重复以下内容，杜绝复述这些已知观点信息**
{cumulative_digest}

**可用上下文**：
- 标记概览：{marker_overview}
- 已检索内容：{retrieved_content}
- 先前分析摘要：{scratchpad_summary}
- 已处理数据块：{previous_chunks_context}

**输出要求**：
- `step_id`: 步骤ID（整数）
- `findings`: 完整的发现对象，包括：
  - `summary`: 核心发现摘要
  - `article`: 完整文章（必须充分回答步骤问题）
  - `points_of_interest`: 结构化兴趣点
  - `analysis_details`: 详细分析
- `insights`: 关键洞察
- `confidence`: 分析信心（0.0-1.0）
- `completion_reason`: 完成原因（如"已整合可用证据完成闭环分析"）

**重要约束**：
- **不要输出 `requests` 字段** - 此字段不在本阶段的输出格式中
- **只关注输出 `findings` 对象** - 这是本阶段的唯一输出目标
- 必须提供完整的 `findings` 对象，包括所有必需字段

**语言要求（重要）**：
- **所有输出必须使用中文**：无论源内容使用何种语言（英语、日语、韩语等），所有分析结果、摘要、洞察、论点、证据描述等都必须用中文表述。
- **跨语言术语引用**：当遇到专业术语、专有名词、品牌名称或关键概念时：
  - 优先使用中文表述，并在首次出现时提供原文（括号标注）
  - 对于没有标准中文翻译的术语，使用中文音译或描述性翻译，并附原文
- **引用原文的处理**：
  - 在`quote`字段中，如果原文是外文，保留原文并添加中文翻译
  - 格式：`"原文内容（中文翻译）"` 或 `"中文翻译[原文: Original Text]"`
  - 在`supporting_evidence`、`description`等字段中，优先使用中文，必要时提供原文对照
- **一致性**：确保整个输出中同一术语的中文表述保持一致

**示例输出**：
{{
  "step_id": {step_id},
  "findings": {{
    "summary": "核心发现摘要（中文，避免重复，聚焦结论+关键证据）。所有输出必须使用中文，即使源内容为其他语言。",
    "article": "完整文章（中文，必须充分回答步骤问题）：综合运用检索证据与专业知识，直接回答步骤目标问题，提供基于证据和推理的完整答案，而非仅总结检索内容。先概览后深入，结合证据与推理构建完整论证链条。",
    "points_of_interest": {{
      "key_claims": [
        {{
          "claim": "核心论点（中文表述，必要时附原文）",
          "supporting_evidence": "支持证据（中文，原文引用需标注）",
          "relevance": "high"
        }}
      ],
      "notable_evidence": [
        {{
          "evidence_type": "fact",
          "description": "证据描述（中文）",
          "quote": "原文引用（如需，格式：原文（中文翻译））"
        }}
      ],
      "controversial_topics": [
        {{
          "topic": "争议话题（中文）",
          "opposing_views": ["观点1（中文）", "观点2（中文）"],
          "intensity": "medium"
        }}
      ],
      "surprising_insights": ["意外洞察（中文表述）"],
      "specific_examples": [
        {{
          "example": "具体例子（中文，术语附原文）",
          "context": "上下文说明（中文）"
        }}
      ],
      "open_questions": ["开放问题（中文）"]
    }},
    "analysis_details": {{
      "five_whys": [
        {{
          "level": 1,
          "question": "为什么会出现X现象？（中文）",
          "answer": "因为Y原因...（中文）"
        }},
        {{
          "level": 2,
          "question": "为什么会有Y原因？（中文）",
          "answer": "因为Z根本原因...（中文）"
        }},
        {{
          "level": 3,
          "question": "为什么...？（中文）",
          "answer": "因为...（中文）"
        }},
        {{
          "level": 4,
          "question": "为什么...？（中文）",
          "answer": "因为...（中文）"
        }},
        {{
          "level": 5,
          "question": "为什么...？（中文）",
          "answer": "因为...（中文）"
        }}
      ],
      "assumptions": ["假设1（中文）", "假设2（中文）"],
      "uncertainties": ["不确定性1（中文）", "不确定性2（中文）"]
    }}
  }},
  "insights": "关键洞察（一句话要点，必须使用中文）",
  "confidence": 0.85,
  "completion_reason": "已整合可用证据完成闭环分析"
}}

