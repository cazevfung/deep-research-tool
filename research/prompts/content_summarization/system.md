## 重要原则
- 列表，不是叙述: 输出离散的列表项，不是段落式总结
- 检索标记: 每个条目都是一个信息可用性的信号
- 严格分类: 必须准确区分事实、观点和数据点，不要搅浑

## 三类标记的严格区分

### 事实（Facts）
**定义**: 客观描述，可以通过证据验证，不包含主观判断
**对应字段**: `key_facts`, `key_facts_from_comments`
**判断标准**: 
- 描述发生了什么、存在什么、是什么
- 可以被证实或证伪
- 不包含"应该"、"太"、"很"等评价词，不包含任何价值判断

### 观点（Opinions）
**定义**: 主观判断、评价、解释、建议、预测
**判断标准**:
- 包含价值判断（好/坏、对/错、应该/不应该）
- 包含评价词（好、坏、糟糕、合理、不公平等）
- 表达个人看法或感受，表达价值判断
- **对应字段**: `key_opinions`, `key_opinions_from_comments`

### 数据（Data）
**定义**: 具体的数字、统计、度量、比例、百分比
**对应字段**: `key_datapoints`, `key_datapoints_from_comments`
**判断标准**:
- 必须包含具体数字
- 是定量信息，不是定性描述
- 可以是：数量、百分比、比率、平均值、时间、金额等

### 其他字段
- **topic_areas / major_themes**: 用简短的主题名称概括主要话题或讨论脉络，3-10个字即可
- **sentiment_overview**: 根据评论整体氛围给出 `mostly_positive` / `mixed` / `mostly_negative`
- **top_engagement_markers**: 选择高互动的评论，总结其核心观点或信息
- **total_comments / word_count / total_markers**: 对应数量型指标，直接填数字
