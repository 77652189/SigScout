# SigScout 架构变更记录（ADR Log）

维护说明：这是架构层面重大变更的日志，按时间倒序排列（最新在最上面）。只记录"改了什么结构、为什么改、留下了什么后果/待办"，不记录纯文案措辞调整。日常小改动看 `git log` 就够，不需要在这里补记。这份文档同时以 ADR 形式存在 codebase-memory-mcp 图数据库里（`manage_adr(project="C-Users-63097-Documents-CursorProject-SigScout", mode="get")`），两处内容应保持一致；以后更新时两边都要改。

---

## 2026-07-28 — 耦合与过大文件审计，产出拆分重构计划（提案，未实施）

**commit**：无代码改动，纯审计+文档；计划见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md)。

**做了什么**：用 codebase-memory-mcp 的图查询（`get_architecture`/`search_graph`/`query_graph`）对全代码库做了一次量化审计。

**发现**：
- `ui/streamlit_app.py`（1839 行）和 `services/screening.py`（898 行，含 160 行的 `screen_uniprot_candidates` 单方法）是两个最大的问题文件；`services/fusion_constructs.py`（652 行）、`services/source_protein_annotation.py`（455 行）次之。
- `_safe_int`/`_safe_float`/`_truthy`/`_now_iso`/`_json_dumps` 等小工具函数在 2-4 个文件里各自重复实现。
- `fusion_constructs_to_csv`/`_to_fasta` 与 `services/exports.py` 的写法是同一种 StringIO+DictWriter 模式的重复发明。
- `services/experimental_exploration.py` 仅为借用 `signal_peptide_identity` 就依赖了整个 `screening.py`。
- `ui/streamlit_app.py` 绕过 `services/__init__.py` 直接 import 5 个 service 子模块；`services/__init__.py` 的 `__all__` 本身也没跟上实际用法。
- UI 层（`streamlit_app.py`、`experimental_browser.py`）零自动化测试覆盖。

**后果/待办**：详细的分阶段拆分方案见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md)，**尚未开始执行**。其中 Phase 5（`services/__init__.py` 到底该不该是唯一导入入口）是一个开放决策，本次审计没有替用户下结论。

---

## 2026-07-28 — 新增湿实验反馈闭环 + 融合构建多目标预设化

**commit**：`c8e2d3b`（功能）、`a4f68a3`（文档）

**做了什么**：
- 新增 `services/experimental_feedback.py`（解析/加载/保存湿实验测量 CSV）、`services/experimental_evidence.py`（按精确序列把反馈匹配回候选/构建）、`services/experimental_exploration.py`（`build_experiment_guided_exploration`：用已测数据的正/中/低表现锚点，通过 Levenshtein 序列相似度为未测候选打分，四通道配额选出下一轮测试面板）。
- 新增 `ui/experimental_browser.py`，嵌入"代表序列与下载 → 候选浏览"页面（不是独立导航项）；`streamlit_app.py` 新增顶层导航"实验反馈"，用于单独查看/导入测量结果。
- `services/screening.py` 新增 `_merge_preserved_source_annotations`：UniProt 刷新时保留已完成的来源蛋白注释，避免刷新一次就要重新人工评估一遍。
- `services/fusion_constructs.py` 从单目标硬编码序列升级为 `FUSION_TARGET_PRESETS` 注册表（`FusionTargetPreset` 数据类），构建结果新增 `target_key`/`target_label` 字段，FASTA header 带上目标标识。

**为什么**：把规则/USPNet 预测和真实湿实验结果连起来，让下一轮候选选择基于实测数据而不是只靠预测；同时把融合构建从"一次只服务一个目标蛋白"改成可注册多个目标预设。

**后果/待办**：**实验反馈闭环这次没有跟着多目标化**——`streamlit_app.py`/`ui/experimental_browser.py` 里的路径（`local_runs/experimental_feedback/opn_measurements.csv`）、`target_key`、session key 都还是单目标硬编码。如果以后要给第二个目标蛋白接入湿实验数据，需要先把这些硬编码换成参数化（按 `FUSION_TARGET_PRESETS` 的 key 来定路径/键名），现在还没有人做这件事，也没有 issue 跟踪，写在这里防止遗忘。

**顺带修复的既有问题**：推送前发现 README 里重新出现了具体目标蛋白名称、UniProt accession 和一篇点名该蛋白的文献引用，与 `3be1de2` 建立的保密边界冲突（见下面 2026-07-07 条目）。推送前已重新脱敏，详见 [REQUIREMENTS.md](REQUIREMENTS.md) 第 5 节。

---

## 2026-07-07 — README 移除具体目标蛋白名称

**commit**：`3be1de2`

**做了什么**：把 README 项目定位/工作流描述里的具体目标蛄白名称替换成通用"目标蛋白"措辞。

**为什么**（原始 commit message）："Same confidentiality boundary as pcSecYeastSpecies applies here - replace specific target protein names with generic 'target protein' language."

**后果/待办**：这是**只针对 README 的**保密边界，代码/测试/数据文件里的真实目标蛋白名称不受影响、可以继续使用。任何后续修改 README 的人都要意识到这条边界依然生效（2026-07-28 那次险些被新 diff 意外撤销，见上文）。

---

## 2026-07-03 — 融合构建工作流 + Streamlit UI 大幅扩张

**commit**：`a479129`（功能，+1572/-78，6 个文件）、`1d9b51a`（纯 README 措辞重排，非结构变更）

**做了什么**：新增 `services/fusion_constructs.py`（614 行）：AC/ABC 融合构建、定位结果导入、构建打分；`ui/streamlit_app.py` 一次性 +743 行——这是它从"还算正常大小"变成"当前 1839 行巨型文件"的主要起点。`services/__init__.py` 开始重导出 fusion 相关符号。

**后果/待办**：这次提交之后，`streamlit_app.py` 的体量问题就已经种下了，只是当时还没有触发拆分讨论。也是本次 2026-07-28 审计里"最大问题文件"结论的历史根源。

---

## 2026-06-18 — 来源蛋白路线注释 + 移除单目标 preset 文件

**commit**：`b720349`（+/- 多个文件，含删除 `src/sigscout/presets/opn.py`，132 行）

**做了什么**：新增 `services/source_protein_annotation.py` 路线判定引擎（数据驱动，读 `data/source_protein_route_map.json`）、`adapters/quickgo.py`（QuickGO/GOA 证据）；同时**删除了 `src/sigscout/presets/opn.py`**——项目从"内置一个硬编码的单目标 preset 文件"转向更通用的候选库/screening service 结构。`services/screening.py` 当次 +183 行。

**后果/待办**：`presets/` 这层被移除后，单目标硬编码并没有被彻底清干净——`core/paths.py` 的 `opn_saved_screening_dir` 属性名，以及本次（2026-07-28）新增的实验反馈闭环路径/键名，都还带着这次重构之前遗留下来的 "opn" 字面量。这是一条跨越三次提交、一直没被彻底解决的命名残留，值得在下次碰这块代码时顺手清理。

---

## 2026-06-17 — 项目初始化

**commit**：`e0e89e8`

**做了什么**：建立项目骨架：`core/`（models/inputs/paths）、`adapters/`（uniprot/uspnet/process_runner）、`services/`（初版）、`cli.py`、`presets/opn.py`（单目标硬编码预设）。当时的默认演示对象是单一目标蛋白在毕赤酵母中的分泌表达候选筛选——这也是后续所有 `opn` 字面量命名残留的源头。

**后果/待办**：无——这是起点，不是遗留问题。
