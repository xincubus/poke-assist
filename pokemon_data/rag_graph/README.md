# rag_graph - GraphRAG 知识图谱

> **状态：已终止（2026-05-10）**
>
> 本模块不再维护和开发。Step 1-3 的数据导入已完成，Step 5 代码已就绪但未全量运行。
> 终止原因：当前查询场景以单跳为主（查实体属性、伤害计算、阈值搜索），结构化 SQL + RAG 混合检索已能覆盖，
> 图谱方案投入产出比不划算（Step 5 全量预估 500M+ tokens，后续 Step 6-9 还需数周工作量）。
> 代码和数据保留在原位，不删除，不接续。如未来产品方向偏向多跳策略推荐/配队分析，可考虑重启。

---

SQLite-based 知识图谱存储与构建。原目标：用 52poke Wiki（73K 页）+ 结构化宝可梦数据构建多跳实体关系图，解决"波荡水晴天队"这类需串联 5+ 实体的查询。

## 文件

| 文件 | 说明 |
|---|---|
| `graph_db.py` | `GraphDB` 类：4 张表（nodes/edges/aliases/extraction_log）+ 7 个索引 + CRUD + `upsert_edge()` |
| `graph_import_structured.py` | **Step 2**：从 pokemonData.db 导入 5050 个结构化节点 + 110K 条结构化边（3.7 秒）|
| `graph_import_wiki.py` | **Step 3**：从 wiki_meta.db + wikitext_cache 导入 45K wiki_page + 208K wiki_section + 558K mentions 边（11 分钟）|
| `graph_extract.py` | **Step 5**：LLM 抽取 wiki 页面语义关系 → graph_edges（`source='llm_extracted'`），代码就绪但未全量运行 |
| `graph.db` | 图数据库文件（~223MB）|

## 表结构（4 张）

- **graph_nodes**：`node_id`（PK）、`node_type`、`name_zh/en/ja`、`properties`(JSON)、`source`、`embedding`、时间戳
- **graph_edges**：`source_id`、`target_id`、`edge_type`、`weight`、`properties`、`source`、`evidence_count`、`contexts`（UNIQUE 三元组）
- **graph_entity_aliases**：`alias`、`node_id`、`alias_type`、`confidence`
- **graph_extraction_log**：`page_id`、`section_id`、`status`、`model`、`input/output_tokens`、`error_msg`

## 已完成的步骤

| Step | 状态 | 说明 |
|---|---|---|
| Step 1: GraphDB 类 | ✅ 完成 | `graph_db.py`，SQLite 存储 + CRUD |
| Step 2: 结构化导入 | ✅ 完成 | 5K 节点 + 110K 边 + 9623 别名 |
| Step 3: Wiki 导入 | ✅ 完成 | 45K wiki_page + 208K wiki_section + 558K mentions 边 |
| Step 5: LLM 抽取 | 代码就绪，未全量运行 | `graph_extract.py`，通用 prompt + 开放关系集 |
| Step 6-9: 对齐/嵌入/查询/接入 | 未开始 | — |

## Step 5 使用方式（如需重启）

**依赖：** `pip install mwparserfromhell openai`

**API Key：** 自动从 `api/.env` 读取 `LLM_TOOL_USE_API_KEY` / `LLM_TOOL_USE_BASE_URL` / `LLM_MODEL_TOOL_USE`，无需手动 export。也支持 `MIMO_API_KEY` / `LLM_API_KEY` / `DEEPSEEK_API_KEY` 作为 fallback。

**关系类型：** 开放集。LLM 可自起 snake_case 关系名（如 `features_move`、`debut_in`、`rival_of`），不限于固定的 12 种。

**Prompt：** 单一通用模板（`api/prompt/graph_extract_prompt.txt`），含 5 个覆盖不同页面类型的 few-shot 示例（宝可梦/招式/特性/状态/TCG+地点）。LLM 举一反三处理所有类型的 wiki 页面。

**放量运行：**
```bash
# 第一轮：100 页试跑（shuffle + 串行）→ 人工 review + 调 prompt
python pokemon_data/rag_graph/graph_extract.py --limit 100 --shuffle

# dry-run 模式：只调 LLM 不写库
python pokemon_data/rag_graph/graph_extract.py --limit 20 --dry-run

# 第二轮：500 页（并发 5）→ 指标统计
python pokemon_data/rag_graph/graph_extract.py --limit 500 --concurrency 5

# 全量（~45K 页，预估 500-600M tokens，7-8 小时并发 5）
python pokemon_data/rag_graph/graph_extract.py --concurrency 5

# 重试失败页
python pokemon_data/rag_graph/graph_extract.py --retry-errors
```

## 指标查询

```sql
-- 抽取进度
SELECT status, count(*), sum(input_tokens), sum(output_tokens)
FROM graph_extraction_log GROUP BY status;

-- 按关系类型统计
SELECT edge_type, count(*), sum(evidence_count)
FROM graph_edges WHERE source='llm_extracted' GROUP BY edge_type;

-- 高证据边（≥3 页证实）
SELECT edge_type, count(*)
FROM graph_edges WHERE source='llm_extracted' AND evidence_count >= 3
GROUP BY edge_type;
```

## 方案文档

- 实施方案：[memory/graphrag_implementation_plan.md](../../../memory/graphrag_implementation_plan.md)
- Step 5 设计文档：[memory/graphrag_step5_plan.md](../../../memory/graphrag_step5_plan.md)
