# SigScout 执行计划：拆分重构

维护说明：这是**可勾选、可执行**的计划文档，对应 [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md) 2026-07-28 审计条目。**全部 6 个 Phase（0/4/3/2/1/5）已于 2026-07-29 完成**，这份文档现在是拆分重构的历史记录 + 经验教训，不再是待办清单。以后如果要对这几个模块做新一轮拆分，先看下面"跨 Phase 的通用教训"。

## 通用约束（每个 Phase 都要遵守）

- 纯内部重组，**不改变任何公开函数签名/行为**——这是文件搬移+import 修正，不是重写。
- 每个 Phase 做完后跑 `python -m pytest -q`（现有 53 个测试），全绿才能进入下一个 Phase。
- Phase 1（UI 拆分）额外要求：手动跑一遍 Streamlit 四个导航页——UI 没有自动化测试，pytest 全绿不代表 UI 没坏。
- 每个 Phase 建议单独提交，commit message 用 `refactor(...): ...`，方便出问题时单独回滚某一步。
- 涉及 README/`docs/` 里目标蛄白名称的部分，本计划不改 README 内容，只改代码结构，不触发 [REQUIREMENTS.md](REQUIREMENTS.md) 第 5 节的脱敏边界。

实际执行顺序：**0 → 4 → 3 → 2 → 1 → 5**（先做风险最低、最独立的，UI 拆分放倒数第二，Phase 5 是决策项放最后）。

**跨 Phase 的通用教训**：不要只按函数名去重/拆分，先读完整函数体、画出跨函数调用关系再动手——Phase 0 发现同名的 `_safe_int` 其实有两种不兼容行为；Phase 4 发现按计划拆分会形成循环 import；Phase 3 发现"留在原文件的函数"反过来调用"要搬走的函数"（`_construct_row` 调 `score_construct`）；Phase 2 发现计划漏掉了 `choose_representative` 的三个隐藏私有依赖，同时发现计划里点名要改的三个文件实际全仓库 grep 后都不需要改；Phase 1 发现了一类新的坑——目录命名可能和目标框架自身的约定冲突（新建的 `ui/pages/` 撞上了 Streamlit 内置的多页面应用自动发现机制），这种问题只有真正启动应用才能发现，`pytest`/`compileall` 完全测不出来；**Phase 5 反过来是个好消息版本的同一个教训**——决策定下来之后，全仓库 grep 确认没有任何调用方需要跟着改，"计划以为要改一堆调用方"这件事本身也需要用真实搜索结果核实，不能假设。六个 Phase 都证明了同一件事：写执行计划时凭经验列出的清单，动手前必须用代码里的真实依赖关系（以及目标框架的实际运行行为）去核实，不能直接当真——无论核实结果是"比想的更麻烦"还是"比想的更简单"。

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

## Phase 3 — 拆 `services/fusion_constructs.py` ✅ 完成于 2026-07-28（635 → 250 行）

- [x] 新建 `services/fusion_scoring.py`（248 行）：`score_construct`、`summarize_localization`、`DEEPLOC_THRESHOLDS`，以及所有 `_*_score` 辅助（`_signal_detail_score`、`_source_context_score`、`_processing_score`、`_risk_score`、`_localization_probability_score`、`_fine_priority_score`、`_contains_any`）。
- [x] 新建 `services/localization_import.py`（137 行）：`import_localization_results`、`_read_delimited_table`、`_extract_first`、`_find_construct_key`、`_localization_id_candidates`、`_normalize_id`、`_safe_column_name`、`LOCALIZATION_*_COLUMNS` 常量、`LocalizationImportResult`。
- [x] 保留在原文件：`build_fusion_constructs`、`_construct_row`、`clean_protein_sequence`、`FusionTargetPreset`/`FUSION_TARGET_PRESETS`、`DEFAULT_*_SEQUENCE` 常量、`_sequence_risks`、`_processing_notes`。
- [x] `fusion_constructs_to_csv`/`_to_fasta` 的 StringIO+DictWriter/80 字符换行逻辑合并进 `services/exports.py`（新增 `rows_to_csv`/`records_to_fasta`，`write_csv`/`write_fasta` 也改为调用它们）；`fusion_constructs.py` 里保留两个同名薄封装函数不变，只是内部转调 `exports.py`。
- [x] 更新 `streamlit_app.py`、`services/__init__.py`、`tests/test_fusion_constructs.py` 的 import。
- [x] 跑 `python -m pytest -q`（53/53 通过）。

**执行时的关键发现和调整：**

1. **两处计划没写到的跨函数依赖**（先读全部函数体、画依赖图才发现的，教训同 Phase 4）：`_construct_row`（留在原文件）内部调用 `score_construct`（要搬走），`import_localization_results`（搬去 `localization_import.py`）内部也调用 `score_construct`（搬去 `fusion_scoring.py`）来对合并定位数据后的构建重新打分。这意味着依赖方向必须是：`fusion_constructs.py → fusion_scoring.py` 和 `localization_import.py → fusion_scoring.py`，`fusion_scoring.py` 本身不能反过来依赖另外两个文件——验证后确认 `fusion_scoring.py` 确实不需要 `fusion_constructs.py`/`localization_import.py` 的任何东西，所以是单向、不循环。
2. **CSV/FASTA 合并没有改变对外暴露的名字**：`tests/test_fusion_constructs.py` 只 import 了 `fusion_constructs_to_fasta`（没有 `_to_csv`），`services/__init__.py`/`streamlit_app.py` 两个都 import 了两者。为了不逼着这几个调用方跟着改 import 路径，`fusion_constructs_to_csv`/`fusion_constructs_to_fasta` 两个公开函数**继续留在 `fusion_constructs.py`**，只是函数体改成调用 `exports.py` 新增的 `rows_to_csv`/`records_to_fasta`——"合并进 exports.py" 指的是消灭重复实现的算法本体，不是强制搬迁公开入口。
3. **CSV 换行符不是同一个行为，逐字节验证过**：原来的 `write_csv`（写文件）没有显式设置 `lineterminator`，走 `csv` 模块默认值 `\r\n`；原来的 `fusion_constructs_to_csv`（返回字符串）显式设了 `lineterminator="\n"`。新的共享核心 `_csv_body(rows, *, lineterminator)` 把这个差异做成参数，`write_csv` 传 `"\r\n"`、`rows_to_csv` 传 `"\n"`——用脚本实际读了两边输出的原始字节确认过完全一致（含 `write_csv` 对空 `rows` 时仍然写一行只有 BOM+换行的"空表头"，`rows_to_csv([])` 则直接返回空字符串，这两者行为本来就不同，都保留了原样）。
4. `score_construct`/`summarize_localization` 是真正物理搬家（不是留壳），所以 `tests/test_fusion_constructs.py`、`streamlit_app.py`、`services/__init__.py` 三处的 import 语句都要相应拆开成从 `fusion_scoring.py`/`localization_import.py` 分别导入，这点在计划里已经预期到了。

风险：中，已验证（`score_construct`/`summarize_localization` 被三处调用，主要是移动+改 import，逻辑不变；CSV/FASTA 字节级行为经脚本核实无变化）。

---

## Phase 2 — 拆 `services/screening.py` ✅ 完成于 2026-07-28（884 → 857 行；god-method 160 → 39 行）

- [x] 新建 `services/similarity.py`（115 行）：`cluster_similar_signal_peptides`、`choose_representative`、`signal_peptide_identity`、`_levenshtein_distance`、`_is_similar_but_not_identical`、`SIMILARITY_IDENTITY_THRESHOLD`。
- [x] 更新 `services/experimental_exploration.py`：改成从 `services/similarity.py` import `signal_peptide_identity`，不再依赖整个 `screening.py`。
- [x] 把 `SignalPeptideScreeningService.screen_uniprot_candidates`（160 行）拆成同一个 class 下的 6 个私有步骤方法：`_discover_step`（34 行）、`_build_initial_summary`（41 行）、`_empty_screening_result`、`_rule_score_step`、`_uspnet_merge_step`、`_similarity_step`、`_finalize_screening_result`（49 行），`screen_uniprot_candidates` 本身收缩到 **39 行**，只负责按顺序调用。
- [x] 更新 `services/__init__.py`、`tests/test_screening.py` 里对 `cluster_similar_signal_peptides`/`choose_representative`/`signal_peptide_identity` 的 import 来源。
- [x] 跑 `python -m pytest -q`（53/53 通过，含 `test_refresh_preserves_completed_source_protein_annotations`）。

**执行时的关键发现和调整：**

1. **`choose_representative` 有隐藏依赖，计划的清单不完整**：`choose_representative` 内部调用 `_representative_sort_key`，而 `_representative_sort_key` 又调用 `_uspnet_supports_signal_peptide` 和 `_reviewed_or_strong_evidence`——这三个私有辅助函数只被这条链路用到，计划原来的清单没写它们，但必须跟着一起搬，否则 `choose_representative` 会在新文件里找不到依赖。
2. **计划里提到要改的 `cli.py`、`ui/streamlit_app.py`、`ui/experimental_browser.py` 三个文件，实际都不需要改**：全仓库 grep 确认这三个文件都没有直接 import `cluster_similar_signal_peptides`/`choose_representative`/`signal_peptide_identity`——它们只通过 `SignalPeptideScreeningService`/`services/__init__.py` 间接用到。实际需要改 import 的只有 `services/__init__.py` 和 `services/experimental_exploration.py`（原计划就点名要修的耦合问题），外加 `tests/test_screening.py`（计划没提，但这几个符号确实物理搬家了，跟 Phase 3 的 `score_construct` 一样需要同步改测试文件的 import）。
3. **god-method 拆分用"可变字典/列表原地更新"而不是每步返回新增量**：`summary` dict 和 `errors` list 在各步骤方法之间以引用传递、原地 `update`/`append`，和原来单一大方法里的写法完全一致，只是分散到几个方法调用里——没有为了"更干净"改成每步返回增量再合并，那样是更大的设计变动，超出"拆分不改行为"的范围。
4. **`annotate_persisted_source_proteins`（74 行）现在是 `screening.py` 里最长的方法**，但它不在本次 Phase 2 范围内（计划只点名了 `screen_uniprot_candidates`），没有动它——如果以后还要继续瘦身 `screening.py`，这是下一个候选。

风险：中，已验证（in-degree 最高的文件，但外部消费者比计划设想的少，改动范围可控）。

---

## Phase 1 — 拆 `ui/streamlit_app.py` ✅ 完成于 2026-07-29（1826 → 60 行）

参照已经拆出去的 `ui/experimental_browser.py` 的模式。

- [x] 新建 `ui/_shared.py`（375 行）：`_css`、`PATHS`/service 工厂函数（`_local_screening_service`、`_example_screening_service`、`_load_result`）、`_load_representative_frames`、`_ensure_display_columns`、`_sorted_unique`、`_render_pagination_controls`（+ `_clamp_page`/`_set_page`/`_set_page_from_widget`）——这些是真正跨页面共用的部分。
- [x] 新建 `ui/views/screening.py`（134 行）：`render_screening`、`render_source_protein_annotation`、`render_help`、`_render_summary`、`_render_source_annotation_interpretation`。
- [x] 新建 `ui/views/representatives.py`（461 行）：`render_representatives`、候选浏览/卡片/筛选/分页、代表序列表格/分布面板、下载区。
- [x] 新建 `ui/views/fusion_localization.py`（680 行）：`render_fusion_localization`、融合生成面板/下载/序列卡片/复制面板、定位导入/缓存/排序。
- [x] 新建 `ui/views/experimental_feedback.py`（165 行）：`render_experimental_feedback`、`_render_experimental_feedback_import`/`_results`/`_sequence_details`。
- [x] `streamlit_app.py` 收缩到 **60 行**：只剩 sys.path 兼容代码、4 个页面 render 函数的 import、`main()` 导航分发、`__main__` 守卫。
- [x] 手动验证：启动 `streamlit run`，依次点开全部 4 个导航项、10 个子页（含"OPN 实验视图"和"导入 DeepLoc 结果"两个数据量最大的视图），确认渲染和交互都正常，控制台零报错。
- [x] 跑 `python -m pytest -q`（53/53 通过）。

**目录名改成了 `ui/views/` 而不是计划里写的 `ui/pages/`——这是本 Phase 唯一的实质性偏差，原因很重要：**

Streamlit 有一个内置的多页面应用（multi-page app）功能：只要主脚本旁边存在一个字面量叫 `pages/` 的目录，Streamlit 会自动扫描该目录下每个 `.py` 文件，在侧边栏顶部生成一份独立的自动导航列表（`streamlit app` / `screening` / `representatives` / `fusion_localization` / `experimental_feedback`）。这几个新文件只是普通的函数定义模块，没有独立可渲染的入口，被 Streamlit 当成"页面"点开会是空白/报错页。这个问题**只有实际启动 Streamlit 才能发现**——`python -m pytest -q` 和 `python -m compileall` 都不会触发这条 Streamlit 运行时逻辑，是纯 UI 框架层面的命名冲突。手动验证一开始（改名前）就看到侧边栏顶部多出一份不该有的导航列表，确认原因后把目录整体改名为 `ui/views/`，问题消失，其余代码不用改。

其余按原计划执行的部分：`_format_number` 和 `_download_file_button` 原计划设想是跨页面共享（放进 `_shared.py`），但逐个追踪调用关系后发现 `_format_number` 只被 `fusion_localization.py` 内部用到、`_download_file_button` 只被 `representatives.py` 内部用到——都不是真正跨页面共享，所以分别放进了各自的页面文件，没有塞进 `_shared.py`。

**发现但未处理（保留原样，只是挪了位置）**：`_render_representative_table`（47 行）和 `_render_representative_workbench`（13 行）在 `ui/views/representatives.py` 里，通过 codebase-memory 的调用图确认它们 in-degree 为 0——`main()` 能到达的调用链完全没有用到这两个函数，看起来是早期设计（可能是"候选浏览"卡片视图取代表格视图之前）留下的死代码。Phase 1 的范围是纯搬移，没有删除任何代码，这两个函数原样保留在新文件里，只是标记出来——是否删除需要你决定。

风险：高，已验证。`_shared.py`/`ui/views/` 之间没有循环 import（`_shared.py` 不依赖任何页面模块）。

---

## Phase 5 — `services/__init__.py` 的导入契约 ✅ 完成于 2026-07-29（选定方案 B）

现状（决策前）：`services/__init__.py` 的 `__all__` 已经和实际用法脱节（`ui/streamlit_app.py`、`ui/experimental_browser.py` 一直在绕过它直接 import 子模块）。二选一，**由用户决定的方向**：

- 方案 A：把 `services/__init__.py` 修成唯一入口，补齐所有缺失的重导出，把所有 UI/CLI 的 import 都改成从 `sigscout.services` 导入。
- **方案 B（已选定）**：放弃 `__init__.py` 的精选重导出，只保留必要的包初始化，所有调用方直接 `from sigscout.services.xxx import yyy`。

- [x] 决定方案：**B**。
- [x] 按方案 B 改完所有调用方。
- [x] 跑 `python -m pytest -q`。

**执行发现：全仓库 grep 确认没有任何调用方需要改。** 搜索 `from sigscout.services import` 和 `sigscout.services.` 两种写法后发现：`tests/`、`cli.py`、`ui/_shared.py`、`ui/views/*.py`、`ui/experimental_browser.py`，以及 `services/` 内部所有跨子模块引用，全部已经是 `from sigscout.services.具体子模块 import 具体符号` 的写法——没有任何地方通过 `sigscout.services`（包级别）导入过东西。也就是说 `services/__init__.py` 里那份精选重导出列表，从头到尾都没有真正的消费者，纯粹是摆设，跟哪个 Phase 拆没拆都无关。

执行内容：把 `services/__init__.py` 的全部重导出和 `__all__` 删掉，换成一行注释说明"为什么故意留空"（防止以后有人看到空文件觉得是遗漏，顺手把重导出加回去）。跑 `python -m compileall`/`python -m pytest -q`（53/53）/`python -m sigscout.cli --help` 都正常；额外启动了一次 Streamlit 确认页面正常加载，无 console 报错。

风险：低，已验证——这是全流程里改动最小的一个 Phase。

---

## 完成标准 ✅ 全部达成（2026-07-29）

- [x] `python -m pytest -q` 全绿（53/53，全程六个 Phase 都保持绿）。
- [x] `python -m compileall src tests sigscout` 无报错。
- [x] 手动跑 Streamlit 全部 4 个导航项、10 个子页无异常（Phase 1 前后各做过一次完整基线比对；Phase 5 后又单独确认过一次启动无误）。
- [x] 重新跑 codebase-memory-mcp 索引，确认最大文件行数、重复辅助函数数量都下降——见 [ARCHITECTURE.md](ARCHITECTURE.md) 各章节的行数表格和已知问题清单，已随每个 Phase 同步更新。
- [x] [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md) 补了变更记录，codebase-memory-mcp 里的 ADR（`manage_adr`）每个 Phase 完成后都同步更新过。

**拆分重构计划到此结束。** 后续如果代码库继续增长、又出现新的过大文件/耦合问题，参照这份文档的方法论重新走一遍流程（审计 → 画依赖图 → 分 Phase 执行 → 每步验证 → 更新文档），不需要照搬这里的具体 Phase 编号。
