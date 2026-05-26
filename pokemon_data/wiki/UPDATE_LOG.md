# Wiki 数据更新记录

## 更新日志

### Wiki 文件

| 日期 | 操作 | 说明 |
|------|------|------|
| 2026-05-10 | 新建 | 首次批量下载 52poke Wiki wikitext 文件，存入 `wikitext_cache/` |
| 2026-05-20 | 更新 | 重新下载最新 wikitext 文件 |

### Wiki → 数据库同步

| 日期 | 操作 | 范围 | 说明 |
|------|------|------|------|
| 2026-05-20 | 更新 | moves 全量 | 已通过 `sync_detector.py --apply` 写入数据库 |
| 2026-05-20 | 更新 | abilities 全量 | 已通过 `sync_detector.py --apply` 写入数据库 |
| 2026-05-20 | 更新 | status 全量 | 已通过 `sync_detector.py --apply` 写入数据库 |
| 2026-05-20 | 更新 | pokemons 全量 | 已通过 `run_sync_pokemons.py` 检测，无有效变更（LLM 误报已过滤） |
| 2026-05-21 | 更新 | items 全量 | 14 条有效变更（6 fling_power + 8 category），已通过 `apply_sync_items.py` 写入 |
| 2026-05-21 | 更新 | items 全量 | 517 条新增道具（ZA Mega 石、野餐、掉落物等）+ 1 条重命名（诅咒之符→咒术之符），已写入 |
| 2026-05-21 | 更新 | moves/abilities/pokemons/status 全量 | 全量同步检测 + 新增条目检查，已修复全角/半角匹配 bug |

### 工具改进

| 日期 | 说明 |
|------|------|
| 2026-05-21 | 所有 `run_sync_*.py` 新增 `--new-only` 参数（只检测新增，跳过过期分析） |
| 2026-05-21 | 所有 `run_sync_*.py` 新增 `--until` 截止日期参数 |
| 2026-05-21 | 所有 `run_sync_*.py` 批量模式新增 Phase 1 新条目检测 + `.md` 摘要自动生成 |
| 2026-05-21 | `apply_sync_items.py` 新增 `--new-only` 支持插入新增条目 |
| 2026-05-21 | `sync_detector.py` 修复全角字母/数字→半角归一化（`to_simplified`） |
| 2026-05-21 | `sync_detector.py` 修复 `db_names` 未做归一化导致的误匹配 |
| 2026-05-21 | `sync_detector.py` 修复 `wiki_title` 带后缀无法匹配 `db_names` 的 bug |
| 2026-05-21 | `sync_detector.py` items 新增条目 prompt 加入 54 个 PokeAPI 分类映射 |

---

## 脚本使用

### 1. Wiki 文件下载（`download_wiki.py`）

```bash
# 枚举全量页面列表（~30秒，73K+页）
python pokemon_data/wiki/download_wiki.py --refresh-list

# 下载/更新所有页面（~10-20小时，支持断点续传）
python pokemon_data/wiki/download_wiki.py

# 只处理前N页（测试用）
python pokemon_data/wiki/download_wiki.py --limit 100

# 强制重新下载所有页面
python pokemon_data/wiki/download_wiki.py --force

# 查看下载统计
python pokemon_data/wiki/download_wiki.py --stats
```

### 2. 数据库同步检测

#### 批量模式（`run_sync_moves.py`）

```bash
# 检测指定日期后 wiki 有更新的 moves 条目，用 LLM 分析变化
python pokemon_data/wiki/run_sync_moves.py --since 2026-04-01

# 只分析单个 wikitext 文件（调试用，跳过全量扫描）
python pokemon_data/wiki/run_sync_moves.py --file "pokemon_data/wiki/wikitext_cache/1009_守住（招式）.wiki"
```

报告输出：`pokemon_data/wiki/sync_reports/`

#### pokemons 同步（`run_sync_pokemons.py`）

```bash
# 检测指定日期后 wiki 有更新的宝可梦条目
python pokemon_data/wiki/run_sync_pokemons.py --since 2026-04-01

# 只分析单个 wikitext 文件（调试用）
python pokemon_data/wiki/run_sync_pokemons.py --file "pokemon_data/wiki/wikitext_cache/159_喷火龙.wiki"
```

#### 完整流程（`sync_detector.py`）

```bash
# 检测 + LLM 分析（支持 moves/abilities/items/status）
python pokemon_data/wiki/sync_detector.py --entity moves --since 2026-04-01

# 只检测不调用 LLM（快速查看过期条目数）
python pokemon_data/wiki/sync_detector.py --entity moves --since 2026-04-01 --quick

# 跳过 API 查询，使用本地缓存时间戳
python pokemon_data/wiki/sync_detector.py --entity moves --since 2026-04-01 --skip-api
```

#### 执行更新（写入数据库）

```bash
# 审核报告后执行更新（会先确认 yes/no）
python pokemon_data/wiki/sync_detector.py --apply pokemon_data/wiki/sync_reports/sync_report_moves_mimo.json
```
