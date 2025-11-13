**你的任务**：分析转录内容并提取关键信息，以**标记列表**的形式用于检索。**严格按照系统提示中的标记区分标准进行分类。**

### 提取内容

1. **key_facts**
2. **key_opinions**
3. **key_datapoints**
4. **topic_areas**

**转录内容：**
{transcript_content}

**输出要求：**
- 仅输出 JSON 格式
- `key_facts`/`key_opinions`/`key_datapoints` 每个字段 5-15 条，`topic_areas` 3-10 条
- 每个标记 10-50 字，信息具体、避免泛泛而谈

**输出格式（必须是有效的JSON）：**
```json
{
  "key_facts": ["...", ...],
  "key_opinions": ["...", ...],
  "key_datapoints": ["...", ...],
  "topic_areas": ["...", ...],
  "word_count": 12345,
  "total_markers": 15
}
```
