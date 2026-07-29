# SigScout 当前目标

维护说明：这是**变化最快**的一份文档，只保留"现在在哪、下一步做什么、有什么会绊人的坑"，不重复其他 4 份文档的内容——细节请点链接过去。每次开始一段新的工作前先看这份文档，做完一件事随手更新，不要让它跟实际进度脱节（这份文档本身过时，就是它想防止的那种"坑"）。

## 现在在哪（截至 2026-07-28）

- 湿实验反馈闭环功能已合并并推送到 `origin/master`（`c8e2d3b`），README 双语已补充说明（`a4f68a3`），需求/架构/架构变更/执行计划/当前目标 5 份工程文档已建立并推送（`02e3756`）。
- **[EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 0（去重共享工具函数）已完成**：新增 `src/sigscout/core/coercion.py`，7 个文件里的重复 `_safe_int`/`_safe_float`/`_truthy`/`_now_iso`/`_json_dumps`/`_coerce_bool`/`_safe_int_value` 全部收敛。执行时发现 `_safe_int` 实际混用了两种不兼容行为（严格版/宽松版），拆成了 `safe_int`/`safe_int_from_float` 两个函数，没有强行合一——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 0。
- **Phase 4（拆 `source_protein_annotation.py`）已完成**：455 → 313 行，新增 `services/evidence_classification.py`（148 行）。执行时发现按原计划拆会形成循环 import，改成了单向依赖并把 `ROUTE_UNKNOWN` 挪去了新文件、把 `_list_values` 挪去了 `core/coercion.py`（改名 `list_values`）——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 4。
- **Phase 3（拆 `fusion_constructs.py`）已完成**：635 → 250 行，新增 `services/fusion_scoring.py`（248 行，打分逻辑）和 `services/localization_import.py`（137 行，DeepLoc/BUSCA 导入）。执行时发现"留在原文件的 `_construct_row`"反过来调用"要搬走的 `score_construct`"，`import_localization_results` 也调用它——确认 `fusion_scoring.py` 不需要另外两个文件的任何东西后，把它做成了单向依赖的叶子模块。`fusion_constructs_to_csv`/`_to_fasta` 两个公开函数没有物理搬家（避免逼三处调用方都改 import），只是内部改成调用 `exports.py` 新增的 `rows_to_csv`/`records_to_fasta`；两者的 CSV 换行符本来就不一样（`\r\n` vs `\n`），合并时用脚本核对字节级输出确认没有改变——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 3。
- **Phase 2（拆 `screening.py`）已完成**：884 → 857 行，新增 `services/similarity.py`（115 行）。更重要的是把 160 行的 `screen_uniprot_candidates` god-method 拆成了 6 个 25-49 行的私有步骤方法，主方法本身收缩到 **39 行**。执行时发现 `choose_representative` 有三个计划没列出的隐藏私有依赖（`_representative_sort_key`/`_uspnet_supports_signal_peptide`/`_reviewed_or_strong_evidence`），也发现计划里点名要改的 `cli.py`/`streamlit_app.py`/`experimental_browser.py` 三个文件实际全部 grep 后都不需要改（它们没有直接 import 这几个符号）——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 2。`experimental_exploration.py` 现在依赖小而专一的 `similarity.py`，不再拖着整个 `screening.py`——这是 Phase 2 明确要修的耦合问题，已解决。
- 四个 Phase 期间 `python -m pytest -q` 全程 53/53 通过。Phase 1/5 尚未开始。

## 下一步（等待决定，不要自己默认选一个就动手）

1. **要不要继续执行 [EXECUTION_PLAN.md](EXECUTION_PLAN.md)？** 按推荐顺序下一步是 Phase 1（拆 `streamlit_app.py`，风险最高，UI 零测试覆盖）。
2. **Phase 5 的开放决策**（`services/__init__.py` 到底该不该是唯一导入入口，方案 A/B）需要先定方向，否则 Phase 1 拆完之后 import 路径可能要再改一遍。
3. 如果暂时不做拆分，继续功能开发时，至少留意下面"已知的坑"里的第 1、4 条。
4. **持续验证的教训**：Phase 0、4、3、2 都发生过"计划写的时候没读全函数体/没检查依赖方向，执行时才发现问题"——执行 Phase 1 之前，同样先枚举每个 UI 辅助函数实际被谁调用，不要只按计划里列的清单假设边界正确。Phase 1 额外风险：UI 零自动化测试，pytest 全绿不能代表没坏，必须手动跑一遍 Streamlit 页面。
5. **顺带发现、还没处理的可选清理项**：`screening.py` 里现在最长的方法是 `annotate_persisted_source_proteins`（74 行），不在任何已完成 Phase 的范围内；如果以后想继续给 `screening.py` 瘦身，这是下一个候选，但不属于当前 5 个 Phase 的既定范围。

## 已知的坑（写代码/改文档前先看一眼）

1. **README 脱敏边界**：改 `README.md`/`README.en.md`（以及本 `docs/` 目录下这 5 份文档）之前，先确认改动里没有具体目标蛋白名称、UniProt accession 或点名该蛋白的文献引用。这条规则已经被违反过一次（2026-07-28 推送前发现），也在这次写 `docs/` 时差点又违反一次。详见 [REQUIREMENTS.md](REQUIREMENTS.md) 第 5 节。
2. **实验反馈闭环是单目标硬编码的**：`opn_measurements.csv` 路径、`target_key="opn"`、`render_opn_experimental_browser`、`fusion_selected_candidate_ids_opn` 这些都还没跟着 `FUSION_TARGET_PRESETS` 多目标化。现在只有一个目标在用，暂时不会炸；一旦要接第二个目标蛄白的湿实验数据，这里必须先改。详见 [ARCHITECTURE.md](ARCHITECTURE.md) 第 4 节。
3. **UI 层零自动化测试**：`ui/streamlit_app.py`、`ui/experimental_browser.py` 没有任何 pytest 覆盖。改 UI 之后 `pytest -q` 全绿不代表没坏，必须手动跑一遍 Streamlit 页面。执行 Phase 1 拆分时这一条风险会被放大，见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 1。
4. **`services/__init__.py` 的 `__all__` 已经和实际用法脱节**：不要假设它是当前的"唯一入口"——`streamlit_app.py`、`experimental_browser.py` 一直在绕过它直接 import 子模块。新增导出时记得两边都检查一下，或者干脆先做 Phase 5 的决策。
5. **仓库根目录有一个未纳入版本控制的 `external.7z`**：不清楚是什么内容、要不要长期保留在工作目录里。如果确认不需要提交，建议加进 `.gitignore` 或直接清理，避免以后有人误以为它该被提交、或者不知道能不能删。**这个由你决定，我没有主动处理。**
6. **没有 `.gitattributes`，行尾风格依赖每台机器的 `core.autocrlf` 设置**（本机是 `true`）：这是为什么这次会话里几乎每条涉及文件改动的 git 命令都弹 "LF will be replaced by CRLF" 警告。目前不影响功能，但换一台 `autocrlf=false` 的机器协作时可能出现整份文件的行尾 diff 噪音。如果以后要多人协作，值得补一个 `.gitattributes` 固定 `* text=auto`。
7. **`core/paths.py` 的 `opn_saved_screening_dir` 属性名残留**：命名没跟上多目标化，见 [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md) 2026-06-18 条目。低优先级，顺手改的时候改。
8. **两个跟 Phase 0 无关的死 import**（执行 Phase 0 时顺带发现，没有处理）：`services/source_protein_annotation.py` 的 `from typing import Iterable`、`ui/streamlit_app.py` 导入的 `annotate_candidate_experimental_evidence`，目前都没有实际用到。低优先级，顺手清理即可。

## 文档地图

- 要改需求/边界 → [REQUIREMENTS.md](REQUIREMENTS.md)
- 要查当前代码结构 → [ARCHITECTURE.md](ARCHITECTURE.md)
- 要查"为什么会变成这样" → [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md)
- 要执行拆分重构 → [EXECUTION_PLAN.md](EXECUTION_PLAN.md)
- 面向用户的功能介绍 → 根目录 `README.md`/`README.en.md`（注意脱敏边界）
- 旧的单文件交接笔记（已停用，指向本目录） → 根目录 `HANDOFF.md`（本地不提交）
