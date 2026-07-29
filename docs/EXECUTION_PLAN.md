# SigScout 执行计划：拆分重构

维护说明：这是**可勾选、可执行**的计划文档，对应 [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md) 2026-07-28 审计条目。做完一个 Phase 就把对应的 `[ ]` 改成 `[x]`，并在该 Phase 末尾补一行"完成于 commit `xxxxxxx`"。

## 通用约束（每个 Phase 都要遵守）

- 纯内部重组，**不改变任何公开函数签名/行为**——这是文件搬移+import 修正，不是重写。
- 每个 Phase 做完后跑 `python -m pytest -q`（现有 53 个测试），全绿才能进入下一个 Phase。
- Phase 1（UI 拆分）额外要求：手动跑一遍 Streamlit 四个导航页——UI 没有自动化测试，pytest 全绿不代表 UI 没坏。
- 每个 Phase 建议单独提交，commit message 用 `refactor(...): ...`，方便出问题时单独回滚某一步。
- 涉及 README/`docs/` 里目标蛄白名称的部分，本计划不改 README 内容，只改代码结构，不触发 [REQUIREMENTS.md](REQUIREMENTS.md) 第 5 节的脱敏边界。

推荐顺序：**0 → 4 → 3 → 2 → 1 → 5**（先做风险最低、最独立的，UI 拆分放最后，Phase 5 是决策项不是纯执行项）。Phase 0、4 已完成，下一步是 Phase 3。

**跨 Phase 的通用教训**（Phase 0 和 Phase 4 都踩到过，后面的 Phase 也要留意）：不要只按函数名去重/拆分，先读完整函数体再动手——Phase 0 发现同名的 `_safe_int` 其实有两种不兼容行为；Phase 4 发现按计划拆分会形成循环 import。两次都是先看了完整实现才发现问题，不是一开始就预料到的。

---

## Phase 0 — 去重共享工具函数 ✅ 完成于 2026-07-28

- [x] 新建 `src/sigscout/core/coercion.py`：`truthy`、`safe_int`、`safe_int_from_float`、`safe_float`、`now_iso`、`json_dumps`。
- [x] 替换重复实现为 import。

**实际执行时和计划有两处出入，记录一下避免以后困惑：**

1. **`_safe_int` 并不是单一实现**——逐个读完函数体后发现两种不同行为混用同一个名字：`adapters/uniprot.py`/`adapters/quickgo.py` 是严格版 `int(str(value))`（`"3.5"` 会失败回退 0）；`ui/streamlit_app.py`/`services/fusion_constructs.py` 是宽松版 `int(float(str(value)))`（`"3.5"` 会得到 3）。这两种行为不等价，为了不改变现有行为，`coercion.py` 里拆成了两个函数——`safe_int`（严格版）和 `safe_int_from_float`（宽松版）——而不是原计划设想的"单一版本 `safe_int`"。
2. **多找到两个同行为的重复**：`services/screening.py` 的 `_coerce_bool` 和 `fusion_constructs.py`/`experimental_exploration.py` 的 `_truthy` 函数体逐字节相同，一并合并进了 `truthy`；`services/screening.py` 另一个独立函数 `_safe_int_value` 和"宽松版 `_safe_int`"函数体也逐字节相同，一并合并进了 `safe_int_from_float`。原计划的清单里没列这两个（当时只是按名字搜的，没有逐个比较函数体），实际去重范围比计划更彻底一点。

替换后的完整清单：

| 目标函数（`core/coercion.py`） | 原来分散在 |
|---|---|
| `truthy` | `fusion_constructs.py: _truthy`、`experimental_exploration.py: _truthy`、`screening.py: _coerce_bool` |
| `safe_int`（严格版） | `adapters/uniprot.py: _safe_int`、`adapters/quickgo.py: _safe_int` |
| `safe_int_from_float`（宽松版） | `ui/streamlit_app.py: _safe_int`、`fusion_constructs.py: _safe_int`、`screening.py: _safe_int_value` |
| `safe_float` | `ui/streamlit_app.py: _safe_float`、`fusion_constructs.py: _safe_float` |
| `now_iso` | `screening.py: _now_iso`、`source_protein_annotation.py: _now_iso`、`adapters/quickgo.py: _now_iso` |
| `json_dumps` | `adapters/uniprot.py: _json_dumps`、`source_protein_annotation.py: _json_dumps` |

验证：`python -m compileall src tests sigscout` 通过；`python -m pytest -q` 53/53 通过；对全部 7 个受影响文件做了全量 grep，确认没有残留的旧函数名调用点或定义。

**顺带发现、本 Phase 未处理的问题**（超出去重范围，没有动）：`services/source_protein_annotation.py` 的 `from typing import Iterable` 和 `ui/streamlit_app.py` 导入的 `annotate_candidate_experimental_evidence` 目前都是未使用的 import——是本次 dedup 之前就存在的死代码，跟这次改动无关，顺手记录在这里，之后有人清理死 import 时可以一起处理。

风险：极低（纯函数，行为不变），已验证。

---

## Phase 4 — 拆 `services/source_protein_annotation.py` ✅ 完成于 2026-07-28（455 → 313 行）

- [x] 保留在原文件：路线匹配引擎——`annotate_source_protein_route(s)`、`_route_matches`、`_load_route_map`、`RouteMatch`。
- [x] 新建 `services/evidence_classification.py`（148 行），移入：证据代码分级常量（`EXPERIMENTAL_*`/`CURATED_*`/`AUTOMATIC_*`）、`evidence_level`、`_all_evidence_codes`、`_go_evidence_prefix`、`evidence_code_label`、`evidence_summary`、`source_route_note`、`format_go`、`confidence_for`。
- [x] 更新 `source_protein_annotation.py` 的 import。
- [x] 跑 `python -m pytest -q`（53/53 通过，`tests/test_source_protein_annotation.py` 覆盖端到端路线判定结果，无需改动）。

**执行时发现计划没预料到的问题——循环 import：**

`evidence_classification.py` 需要用到原文件的 `ROUTE_UNKNOWN`、`RouteMatch`、`_list_values`；但拆分后 `source_protein_annotation.py` 又要反过来 import 新文件里的 6 个函数——两个文件互相 import 会在运行时报 `ImportError`（Python 处理不了这种循环）。解决方式（单向依赖，不再是原计划设想的"新文件单纯从旧文件借东西"）：

- `ROUTE_UNKNOWN` 的定义搬去了 `evidence_classification.py`（它的两个函数 `confidence_for`/`source_route_note` 才是真正拿它做判断的地方），`source_protein_annotation.py` 反过来从新文件 import 回来。
- `RouteMatch` 仍然留在 `source_protein_annotation.py`（它是 `_route_matches` 构造的核心数据结构，这个不动）；`evidence_classification.py` 里两处只是拿它当类型标注，用 `typing.TYPE_CHECKING` 包起来导入，不会在运行时真正 import，从而不构成循环。
- `_list_values` 挪去了 `src/sigscout/core/coercion.py`（改名 `list_values`，公开），因为这是个通用的"值/list 归一化"小工具，跟 Phase 0 收敛掉的那批工具函数是同一类东西，两个文件都从这里拿，谁也不依赖谁。

另外，把 `_evidence_level` 等 8 个函数改成公开名字（去掉下划线）后，`annotate_source_protein_route` 里原来有个局部变量也叫 `evidence_level`，和新 import 进来的同名函数撞名——虽然 Python 语法上不会报错（赋值右边先算完再绑定左边名字），但容易在以后维护时踩坑，所以把这个局部变量顺手改名成了 `level`。

依赖方向变成单向：`source_protein_annotation.py → evidence_classification.py → core/coercion.py`，没有循环。

风险：低，已验证。

---

## Phase 3 — 拆 `services/fusion_constructs.py`（652 行）

- [ ] 新建 `services/fusion_scoring.py`，移入：`score_construct`、`summarize_localization`、`DEEPLOC_THRESHOLDS`，以及所有 `_*_score` 辅助（`_signal_detail_score`、`_source_context_score`、`_processing_score`、`_risk_score`、`_localization_probability_score`、`_fine_priority_score`）。
- [ ] 新建 `services/localization_import.py`，移入：`import_localization_results`、`_read_delimited_table`、`_extract_first`、`_find_construct_key`、`_localization_id_candidates`、`_normalize_id`、`_safe_column_name`、`LOCALIZATION_*_COLUMNS` 常量、`LocalizationImportResult`。
- [ ] 保留在原文件：`build_fusion_constructs`、`_construct_row`、`clean_protein_sequence`、`FusionTargetPreset`/`FUSION_TARGET_PRESETS`、`DEFAULT_*_SEQUENCE` 常量、`_sequence_risks`、`_processing_notes`。
- [ ] 把 `fusion_constructs_to_csv`/`_to_fasta` 合并进 `services/exports.py`（给 `write_csv`/`write_fasta` 增加"返回字符串"而不是"写文件"的变体，两边共用同一份 StringIO+DictWriter 逻辑），删除重复实现。
- [ ] 更新 `streamlit_app.py`、`services/__init__.py` 的 import。
- [ ] 跑 `python -m pytest -q`（重点看 `tests/test_fusion_constructs.py`）。

风险：中（`score_construct`/`summarize_localization` 被 `streamlit_app.py` 和测试同时调用，主要是移动+改 import，逻辑不变）。

---

## Phase 2 — 拆 `services/screening.py`（898 行，最大目标）

- [ ] 新建 `services/similarity.py`，移入：`cluster_similar_signal_peptides`、`choose_representative`、`signal_peptide_identity`、`_levenshtein_distance`、`_is_similar_but_not_identical`、`SIMILARITY_IDENTITY_THRESHOLD`。
- [ ] 更新 `services/experimental_exploration.py`：改成从 `services/similarity.py` import `signal_peptide_identity`，不再依赖整个 `screening.py`。
- [ ] 把 `SignalPeptideScreeningService.screen_uniprot_candidates`（160 行）拆成同一个 class 下的几个私有步骤方法（例如 `_discover_step`/`_rule_score_step`/`_uspnet_merge_step`/`_similarity_step`/`_source_annotation_merge_step`），每个 40-50 行以内，`screen_uniprot_candidates` 本身只负责按顺序调用。
- [ ] 更新 `services/__init__.py`、`cli.py`、`ui/streamlit_app.py`、`ui/experimental_browser.py` 里对 `cluster_similar_signal_peptides`/`choose_representative`/`signal_peptide_identity` 的 import 来源。
- [ ] 跑 `python -m pytest -q`（重点看 `tests/test_screening.py`，含 2026-07-28 新加的 `test_refresh_preserves_completed_source_protein_annotations`）。

风险：中——这是 in-degree 最高的文件（CLI/UI/测试都调），务必先做 Phase 0/3/4 让 `screening.py` 的依赖面先稳定下来，再动它。

---

## Phase 1 — 拆 `ui/streamlit_app.py`（1839 行，风险最高）

参照已经拆出去的 `ui/experimental_browser.py` 的模式。

- [ ] 新建 `ui/_shared.py`：`_css`、`_format_number`、`_download_file_button`、`PATHS`/service 工厂函数（`_local_screening_service`、`_example_screening_service`）等跨页面共用的辅助。
- [ ] 新建 `ui/pages/screening.py`：`render_screening`、`render_source_protein_annotation`、`_render_summary`、`_render_source_annotation_interpretation` 及相关私有辅助。
- [ ] 新建 `ui/pages/representatives.py`：`render_representatives`、候选浏览/卡片/筛选/分页（`_render_candidate_browser`、`_render_candidate_cards`、`_render_candidate_filters`、`_render_pagination_controls` 等）、代表序列表格/工作台/分布面板。
- [ ] 新建 `ui/pages/fusion_localization.py`：`render_fusion_localization`、融合生成面板/下载/序列卡片/复制面板、定位导入/缓存/排序（`_render_fusion_generation_panel`、`_render_localization_import` 等）。
- [ ] 新建 `ui/pages/experimental_feedback.py`：`render_experimental_feedback`、`_render_experimental_feedback_import`/`_results`/`_sequence_details`/`_match_tabs`。
- [ ] `streamlit_app.py` 收缩成只剩 `st.set_page_config`、`main()` 的导航分发、极少量胶水代码（目标 150-200 行）。
- [ ] **在拆之前或拆的过程中**，考虑给可独立测试的纯逻辑辅助（`_sort_localization_results`、`_ensure_display_columns`、`_clamp_page` 等）补单元测试——目前 UI 层零覆盖，这是拆分本身最大的风险来源。
- [ ] 手动验证：启动 `streamlit run`，依次点开"毕赤酵母信号肽筛选"（两个子页）、"代表序列与下载"（四个子页）、"融合定位"（两个子页）、"实验反馈"（两个子页），确认渲染和交互（下载按钮、CSV 导入、分页、引导探索面板）都正常。
- [ ] 跑 `python -m pytest -q`。

风险：高（体量最大 + 零自动化测试 + Streamlit 的 `st.session_state`/多次 rerun 语义容易在拆分时踩坑）。

---

## Phase 5 — `services/__init__.py` 的导入契约（决策项，非纯执行项）

现状：`services/__init__.py` 的 `__all__` 已经和实际用法脱节（`ui/streamlit_app.py`、`ui/experimental_browser.py` 一直在绕过它直接 import 子模块）。需要二选一，**这是需要你决定的方向，不是我能替你定的**：

- **方案 A**：把 `services/__init__.py` 修成唯一入口——补齐所有缺失的重导出（`score_construct`、`FusionTargetPreset`/`FUSION_TARGET_PRESETS`、experimental_feedback 系列函数、`DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE` 等），并把 Phase 1-4 之后所有 UI/CLI 的 import 都改成从 `sigscout.services` 导入，不直接碰子模块。
- **方案 B**：放弃 `__init__.py` 的精选重导出，只保留必要的包初始化，所有调用方直接 `from sigscout.services.xxx import yyy`（即 `experimental_browser.py` 已经在用的风格）。

- [ ] 决定方案 A 或 B。
- [ ] 按决定的方案统一改完所有调用方。
- [ ] 跑 `python -m pytest -q`。

---

## 完成标准（全部 Phase 做完后）

- [ ] `python -m pytest -q` 全绿。
- [ ] `python -m compileall src tests sigscout` 无报错。
- [ ] 手动跑一遍 Streamlit 四个导航页无异常。
- [ ] 重新跑一次 codebase-memory-mcp 的 `get_architecture`/`query_graph` 审计，确认最大文件行数、重复辅助函数数量都下降，更新 [ARCHITECTURE.md](ARCHITECTURE.md) 里的行数表格和已知问题清单。
- [ ] 在 [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md) 补一条"拆分完成"记录，并同步更新 codebase-memory-mcp 里的 ADR（`manage_adr(mode="update")`）。
