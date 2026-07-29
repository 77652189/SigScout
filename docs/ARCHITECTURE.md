# SigScout 架构文档

维护说明：这份文档描述**当前代码的实际结构**（截至 2026-07-29，[EXECUTION_PLAN.md](EXECUTION_PLAN.md) 里的全部 6 个 Phase 均已完成），不是理想状态——理想状态已经和现状基本一致，剩余的已知问题记在各章节和 [CURRENT_GOALS.md](CURRENT_GOALS.md) 里。变更历史见 [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md)。行数/依赖数据来自 codebase-memory-mcp 图索引和实际代码核对，若代码已变化，以实际代码为准。

## 1. 分层总览

```mermaid
flowchart TD
    UI["Streamlit UI<br/>src/sigscout/ui"]
    CLI["CLI<br/>src/sigscout/cli.py"]
    SERVICES["服务层<br/>src/sigscout/services"]
    CORE["核心模型<br/>src/sigscout/core"]
    ADAPTERS["适配层<br/>src/sigscout/adapters"]
    DATA["本地输出<br/>local_runs / CSV / FASTA / JSON"]

    UI --> SERVICES
    CLI --> SERVICES
    SERVICES --> CORE
    SERVICES --> ADAPTERS
    SERVICES --> DATA
```

**服务层内部耦合（已解决）**：`services/__init__.py` 曾经是一份精选重导出（`__all__`），但和实际用法早就脱节——它缺 `score_construct`、`FusionTargetPreset`/`FUSION_TARGET_PRESETS`、`DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE`、experimental_feedback 的导出等，全代码库（UI/CLI/services 内部互相引用/tests）一直是直接 `from sigscout.services.xxx import yyy` 绕过它，从没人真正用过包级入口。[EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 5 里把这个问题摆到台面上让用户决策，用户选择了方案 B——放弃这层封装：全仓库 grep 确认零消费者依赖包级导入后，`services/__init__.py` 被清空为一份说明性注释（6 行），统一改为直接从子模块 import。现在 `services/__init__.py` 不再是"应该同步但没同步"的重导出层，而是刻意留空的。

## 2. 入口层

- **CLI**（`src/sigscout/cli.py`，109 行）：`argparse` 四个子命令 `discover`/`screen`/`annotate-source`/`serve`；只依赖 `SignalPeptideLibraryService`、`SignalPeptideScreeningService`、`USPNetAdapter`——没有直接依赖 fusion/experimental 相关模块，是全代码库里耦合最干净的入口。
- **Streamlit UI**（`src/sigscout/ui/`，[EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 1 完成，`streamlit_app.py` 从 1839 行降到 **60 行**）：见下方"UI 层文件表"。

### UI 层文件表（Phase 1 完成后）

| 文件 | 行数 | 职责 |
|---|---|---|
| `streamlit_app.py` | 60 | sys.path 兼容代码（`streamlit run` 直接执行脚本时让 `sigscout` 包可导入）、`main()`（侧边栏四路导航分发）、`__main__` 守卫。不再包含任何页面渲染逻辑 |
| `_shared.py` | 375 | 跨页面共用：`PATHS`（`ProjectPaths.discover` 结果）、`st.set_page_config`（模块加载时执行一次）、`_css`、`_local_screening_service`/`_example_screening_service`/`_load_result`/`_load_representative_frames`、`_ensure_display_columns`、`_sorted_unique`、`_render_pagination_controls`（+ `_clamp_page`/`_set_page`/`_set_page_from_widget`） |
| `views/screening.py` | 134 | "毕赤酵母信号肽筛选"：`render_screening`、`render_source_protein_annotation`、`render_help`、结果摘要渲染 |
| `views/representatives.py` | 461 | "代表序列与下载"：候选浏览（含 OPN 实验视图切换）/证据分布/相似序列/原始数据四个子页、下载按钮。含两个疑似死代码函数，见下方说明 |
| `views/fusion_localization.py` | 680 | "融合定位"：构建生成面板、DeepLoc/BUSCA 导入、定位缓存、融合序列复制区——UI 层里最大的文件，因为它同时承接 `fusion_constructs`/`fusion_scoring`/`localization_import`/`experimental_evidence` 四个 service 模块的展示逻辑 |
| `views/experimental_feedback.py` | 165 | "实验反馈"：OPN 实验结果展示、CSV 导入与模板 |
| `experimental_browser.py` | 322 | 不属于本次拆分范围（Phase 1 之前就已独立成文件），嵌入 `views/representatives.py` 的"候选浏览"页面，不是独立导航项 |

**命名坑，记录下来避免以后重蹈**：新目录本来想按计划叫 `ui/pages/`，实际建出来后 Streamlit 会把它当成自己的[多页面应用](https://docs.streamlit.io/develop/concepts/multipage-apps)功能目录，自动在侧边栏顶部加一份基于文件名生成的导航列表（这些文件本身不是可独立运行的页面，点开是空白页）。这个问题只有真正 `streamlit run` 起来才会暴露，`pytest`/`compileall` 都测不出来。已改名为 `ui/views/`，问题解决——以后新增 UI 子目录时不要用 `pages` 这个名字。

**已知死代码**：`views/representatives.py` 里的 `_render_representative_table`（47 行）和 `_render_representative_workbench`（13 行），通过调用图确认 in-degree 为 0，`main()` 的可达调用链完全没用到，大概率是早期设计（表格视图/tabs 布局）被"候选浏览"卡片视图取代后留下的。Phase 1 只做纯搬移没有删代码，这两个函数原样保留在新文件里，是否删除需要用户决定。

## 3. 核心模型层（`src/sigscout/core/`）

小而稳定，不在重构范围内：

- `models.py`（71 行）：`SignalPeptideCandidate`（Pydantic，候选的规范表示：leader/signal peptide 序列、来源 UniProt 字段、分类标签）、`CandidateDiscoveryResult`、`UniProtCandidateLibraryResult`、`AA_PATTERN`（标准氨基酸单字母正则）。
- `inputs.py`（66 行）：`CandidateInputProvider`/`TargetProteinInputProvider` 两个 `Protocol`，`CandidateInputBatch`/`TargetProteinInput(Result)` 数据类，`clean_amino_acid_sequence`/`is_standard_amino_acid_sequence`。新增候选输入来源应该实现这两个 Protocol 之一，而不是让 UI 直接解析。
- `paths.py`（46 行）：`ProjectPaths.discover()` 向上找 `pyproject.toml` + `src/sigscout` 定位项目根；`local_runs_dir`、`uspnet_repo`（支持 `USPNET_REPO` 环境变量）等路径属性。**命名残留**：`opn_saved_screening_dir` 属性名仍然写死 `opn`，是早期单目标阶段的命名，没有跟随后续多目标化重构更新。
- `coercion.py`（47 行，[EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 0 新增）：`truthy`/`safe_int`/`safe_int_from_float`/`safe_float`/`now_iso`/`json_dumps`/`list_values`——原本分散在 7 个文件里的重复小工具函数收敛处。`safe_int` 和 `safe_int_from_float` 是两个不同函数（严格/宽松两种数字解析行为），不要当成同一个函数的两种写法。

## 4. 服务层（`src/sigscout/services/`）—— 主要复杂度集中在这里

| 文件 | 行数 | 职责 | 备注 |
|---|---|---|---|
| `library.py` | 192 | `SignalPeptideLibraryService`：候选库管理、CSV 导入校验（`validate_import_csv`）、模板 CSV 生成、委托 UniProt 发现 | 单一职责，清晰 |
| `inputs.py` | 198 | `CsvCandidateInputProvider`/`StaticCandidateInputProvider`/`StaticTargetProteinInputProvider`：`core/inputs.py` Protocol 的具体实现 | 清晰 |
| `rules.py` | 159 | `score_signal_peptide`：N 区正电/H 区疏水核心/C 区切割位点/低复杂度风险显式规则打分 | 清晰，最大函数 76 行 |
| `screening.py` | 857（[EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 2 完成，原 884 行） | `SignalPeptideScreeningService`：`screen_uniprot_candidates` 现在只有 **39 行**，拆成 6 个私有步骤方法（`_discover_step`/`_build_initial_summary`/`_empty_screening_result`/`_rule_score_step`/`_uspnet_merge_step`/`_similarity_step`/`_finalize_screening_result`，各 25-49 行）；另有 `annotate_persisted_source_proteins`、跨刷新保留已完成注释（`_merge_preserved_source_annotations`） | **仍是全代码库最大文件**（其余服务大多被拆分掉了），但不再有单一 160 行的 god-method；现在文件里最长的方法是 `annotate_persisted_source_proteins`（74 行，不在 Phase 2 范围内，未拆）。相似聚类已拆到 `similarity.py`，见下一行 |
| `similarity.py` | 115（Phase 2 新增） | `cluster_similar_signal_peptides`/`choose_representative`/`signal_peptide_identity`/`_levenshtein_distance` | `experimental_exploration.py` 现在依赖这个小文件而不是整个 `screening.py`——Phase 2 明确要修的耦合问题 |
| `source_protein_annotation.py` | 313（[EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 4 完成，原 455 行） | `annotate_source_protein_route(s)`/`_route_matches`/`_load_route_map`/`RouteMatch`：路线匹配引擎（读 `data/source_protein_route_map.json`，按 GO 祖先 + UniProt SL ID + feature type 匹配路线） | 证据分级/格式化职责已拆到 `evidence_classification.py`，见下一行 |
| `evidence_classification.py` | 148（Phase 4 新增） | 证据代码分级常量（`EXPERIMENTAL_*`/`CURATED_*`/`AUTOMATIC_*`）、`evidence_level`/`confidence_for`/`evidence_summary`/`source_route_note`/`format_go`/`evidence_code_label` | 依赖方向：`source_protein_annotation.py → evidence_classification.py`（单向）。`ROUTE_UNKNOWN` 定义在这里（不在 `source_protein_annotation.py`），`RouteMatch` 仍在 `source_protein_annotation.py`、这里只用 `TYPE_CHECKING` 引用类型，避免循环 import——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 4 |
| `fusion_constructs.py` | 250（[EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 3 完成，原 635 行） | `build_fusion_constructs`（多目标预设 `FUSION_TARGET_PRESETS` 下生成 AC/ABC 构建）、`_construct_row`、`clean_protein_sequence`、`_sequence_risks`/`_processing_notes`；`fusion_constructs_to_csv`/`_to_fasta` 留作薄封装，内部转调 `exports.py` | 打分逻辑已拆到 `fusion_scoring.py`，定位导入已拆到 `localization_import.py`，见下两行 |
| `fusion_scoring.py` | 248（Phase 3 新增） | `score_construct`（6 个子打分：signal_detail/source_context/processing/risk/localization_probability/fine_priority）、`summarize_localization`（DeepLoc 概率分桶）、`DEEPLOC_THRESHOLDS` | 不依赖 `fusion_constructs.py`/`localization_import.py`，是纯粹的叶子模块；`fusion_constructs.py`（`_construct_row`）和 `localization_import.py`（`import_localization_results`）都反过来依赖它 |
| `localization_import.py` | 137（Phase 3 新增） | `import_localization_results`（DeepLoc/BUSCA CSV/TSV 解析与 construct_id 匹配） | 依赖 `fusion_scoring.py`（合并定位数据后要重新调用 `score_construct` 打分） |
| `exports.py` | 77 | 通用 `write_csv`/`write_fasta`/`write_json`（写文件版本），以及 Phase 3 新增的 `rows_to_csv`/`records_to_fasta`（返回字符串版本，`fusion_constructs.py` 的两个薄封装函数在用） | `write_csv`/`rows_to_csv` 共用同一个私有 `_csv_body`，但换行符不同（`\r\n` vs `\n`）——这是原本两处实现真实存在的行为差异，合并时保留了，不是新引入的 |
| `experimental_feedback.py` | 244 | 解析/加载/保存湿实验测量 CSV（`ExperimentalFeedbackResult`）、`prepare_experimental_feedback` 校验与类型转换、`summarize_experimental_feedback` | 新增（本次推送） |
| `experimental_evidence.py` | 199 | `annotate_candidate_experimental_evidence`/`annotate_construct_experimental_evidence`/`build_target_experimental_candidates`：按精确清洗后的氨基酸序列把反馈行匹配回候选/构建 | 新增（本次推送） |
| `experimental_exploration.py` | 226 | `build_experiment_guided_exploration`：用已测数据的正/中/低表现锚点，通过 Levenshtein 序列相似度给未测候选打分，四通道配额选面板（正向邻域/通用预测强/多样性/低表现对照） | 曾经仅为借用 `signal_peptide_identity` 就 `import` 整个 `screening.py`；Phase 2 已修复，现在依赖 `similarity.py` |
| `__init__.py` | 6（[EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 5 完成，原 49 行精选重导出） | 刻意留空，只有一段说明性注释，指向应该 import 的子模块写法 | 见第 1 节的耦合解决说明 |

**已知命名残留**：实验反馈闭环目前的路径/键名是**单目标硬编码**的——`ui/views/experimental_feedback.py`/`ui/views/fusion_localization.py` 里读取的固定路径是 `local_runs/experimental_feedback/opn_measurements.csv`，`target_key="opn"` 是字面量；`ui/experimental_browser.py` 的函数名是 `render_opn_experimental_browser`，session key 是 `fusion_selected_candidate_ids_opn`。而同一次推送刚把 `fusion_constructs.py` 从单目标改成了 `FUSION_TARGET_PRESETS` 多目标注册表。也就是说：**融合构建已经多目标化，但实验反馈闭环还没有跟上**——如果以后要给第二个目标蛋白接入湿实验数据，这些硬编码路径/键名会先炸。这是一个具体的"坑"，记录在 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) 里跟踪。

## 5. 适配层（`src/sigscout/adapters/`）

单一职责，未纳入拆分范围（除非后续继续变大）：

- `uniprot.py`（466 行）：`UniProtSignalPeptideSource.discover()`/`rows_from_payload()`/`rows_from_items()`，分页（`_next_link`），从 UniProt JSON payload 里抽取 signal peptide feature、subcellular location、GO terms、evidence text 等一整套字段解析辅助函数。行数大但只服务一个目的（把 UniProt JSON 转成候选行），暂不建议拆分。
- `quickgo.py`（182 行）：QuickGO/GOA cellular component 注释 + GO 祖先查询。
- `uspnet.py`（213 行）：`USPNetAdapter` 包装本地 USPNet-fast 仓库，本机未安装时优雅降级（不阻断规则筛选）。
- `process_runner.py`（42 行）：subprocess 包装。

## 6. 数据层

- `data/source_protein_route_map.json`：来源蛋白路线判定规则（GO 祖先 ID、UniProt SL ID、feature type、证据代码分级），数据驱动，改规则不用改代码。当前 `version: "2026-07-24"`。
- `local_runs/`：运行期输出（UniProt 候选、筛选结果、融合构建、实验反馈 CSV 等），Git 忽略。

## 7. 跨文件重复 — ✅ 已在 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 0 收敛

原先分散重复的小工具函数（`_safe_int`/`_safe_float`/`_truthy`/`_now_iso`/`_json_dumps`，以及执行时额外发现的 `screening.py: _coerce_bool`/`_safe_int_value`）已统一收敛到 `src/sigscout/core/coercion.py`（`truthy`/`safe_int`/`safe_int_from_float`/`safe_float`/`now_iso`/`json_dumps`）。执行细节、发现的行为差异（`_safe_int` 实际有严格版/宽松版两种不兼容行为）见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 0。

## 8. 测试布局

`tests/` 与 `src/sigscout/services|adapters/` 基本一对一镜像命名（`test_screening.py`、`test_fusion_constructs.py` 等），`conftest.py` 提供共享 fixture。截至本文档编写，53 个测试全部通过。**UI 层（`ui/streamlit_app.py`、`ui/_shared.py`、`ui/views/*.py`、`ui/experimental_browser.py`）没有对应测试文件**——这是唯一的覆盖缺口，Phase 1 拆分后依然如此，只能靠手动启动 `streamlit run` 验证。
