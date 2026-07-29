# SigScout 当前目标

维护说明：这是**变化最快**的一份文档，只保留"现在在哪、下一步做什么、有什么会绊人的坑"，不重复其他 4 份文档的内容——细节请点链接过去。每次开始一段新的工作前先看这份文档，做完一件事随手更新，不要让它跟实际进度脱节（这份文档本身过时，就是它想防止的那种"坑"）。

## 现在在哪（截至 2026-07-29）

- 湿实验反馈闭环功能已合并并推送到 `origin/master`（`c8e2d3b`），README 双语已补充说明（`a4f68a3`），需求/架构/架构变更/执行计划/当前目标 5 份工程文档已建立并推送（`02e3756`）。
- **[EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 0/4/3/2/1 全部完成**，只剩 **Phase 5**（`services/__init__.py` 导入契约，需要用户决策，不是纯执行项）。
- **Phase 1（拆 `ui/streamlit_app.py`）已完成**：1826 → **60 行**。新增 `ui/_shared.py`（375 行，跨页面共用）和 `ui/views/{screening,representatives,fusion_localization,experimental_feedback}.py` 四个页面文件。执行时踩到一个新类型的坑：新目录本来想按计划叫 `ui/pages/`，实际建出来后被 Streamlit 自己的多页面应用功能误认成页面目录，自动在侧边栏加了一份多余的导航列表——这个问题只有真正启动 `streamlit run` 才暴露，`pytest`/`compileall` 都测不出来。已改名为 `ui/views/` 解决。手动过了一遍全部 4 个导航项、10 个子页（含数据量最大的"OPN 实验视图"和"导入 DeepLoc 结果"），和 Phase 1 之前的基线逐项比对一致，控制台零报错——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 1。
- 五个 Phase 期间 `python -m pytest -q` 全程 53/53 通过。

## 下一步（等待决定，不要自己默认选一个就动手）

1. **Phase 5 的开放决策**（`services/__init__.py` 到底该不该是唯一导入入口，方案 A/B，见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 5）需要你先定方向——这是拆分重构计划里唯一还没做的事。
2. 如果暂时不处理 Phase 5，继续功能开发时，至少留意下面"已知的坑"里的第 1、3 条。
3. **五个 Phase 一致的教训**：写执行计划时凭经验列出的清单，动手前必须用代码里的真实依赖关系（以及目标框架的实际运行行为，Phase 1 才发现这一层）去核实，不能直接当真——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) 开头的"跨 Phase 通用教训"。
4. **顺带发现、还没处理的可选清理项**：
   - `screening.py` 里现在最长的方法是 `annotate_persisted_source_proteins`（74 行），不在任何已完成 Phase 的范围内。
   - `ui/views/representatives.py` 里的 `_render_representative_table`/`_render_representative_workbench` 两个函数疑似死代码（in-degree 0，`main()` 可达调用链用不到），Phase 1 只做纯搬移没有删代码，原样保留，删不删需要你决定。
   - 这些都不属于当前 5 个 Phase 的既定范围，只是顺带记录。

## 已知的坑（写代码/改文档前先看一眼）

1. **README 脱敏边界**：改 `README.md`/`README.en.md`（以及本 `docs/` 目录下这 5 份文档）之前，先确认改动里没有具体目标蛋白名称、UniProt accession 或点名该蛋白的文献引用。这条规则已经被违反过一次（2026-07-28 推送前发现），也在这次写 `docs/` 时差点又违反一次。详见 [REQUIREMENTS.md](REQUIREMENTS.md) 第 5 节。
2. **实验反馈闭环是单目标硬编码的**：`opn_measurements.csv` 路径、`target_key="opn"`（现在分散在 `ui/views/experimental_feedback.py`/`ui/views/fusion_localization.py` 里）、`render_opn_experimental_browser`、`fusion_selected_candidate_ids_opn` 这些都还没跟着 `FUSION_TARGET_PRESETS` 多目标化。现在只有一个目标在用，暂时不会炸；一旦要接第二个目标蛋白的湿实验数据，这里必须先改。详见 [ARCHITECTURE.md](ARCHITECTURE.md) 第 4 节。
3. **UI 层零自动化测试**：`ui/streamlit_app.py`、`ui/_shared.py`、`ui/views/*.py`、`ui/experimental_browser.py` 没有任何 pytest 覆盖，Phase 1 拆分后依然如此。改 UI 之后 `pytest -q` 全绿不代表没坏，必须手动跑一遍 Streamlit 页面。
4. **`services/__init__.py` 的 `__all__` 已经和实际用法脱节**：不要假设它是当前的"唯一入口"——UI 层一直在绕过它直接 `import` 子模块。新增导出时记得两边都检查一下，或者干脆先做 Phase 5 的决策。
5. **仓库根目录有一个未纳入版本控制的 `external.7z`**：不清楚是什么内容、要不要长期保留在工作目录里。如果确认不需要提交，建议加进 `.gitignore` 或直接清理，避免以后有人误以为它该被提交、或者不知道能不能删。**这个由你决定，我没有主动处理。**
6. **没有 `.gitattributes`，行尾风格依赖每台机器的 `core.autocrlf` 设置**（本机是 `true`）：这是为什么这次会话里几乎每条涉及文件改动的 git 命令都弹 "LF will be replaced by CRLF" 警告。目前不影响功能，但换一台 `autocrlf=false` 的机器协作时可能出现整份文件的行尾 diff 噪音。如果以后要多人协作，值得补一个 `.gitattributes` 固定 `* text=auto`。
7. **`core/paths.py` 的 `opn_saved_screening_dir` 属性名残留**：命名没跟上多目标化，见 [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md) 2026-06-18 条目。低优先级，顺手改的时候改。
8. **一个跟 Phase 0 无关的死 import**（执行 Phase 0 时顺带发现）：`services/source_protein_annotation.py` 的 `from typing import Iterable` 目前没有实际用到，低优先级，顺手清理即可。原来 `streamlit_app.py` 里还有一个未使用的 `annotate_candidate_experimental_evidence` 导入，Phase 1 重写 `ui/views/fusion_localization.py` 时核对每个 import 的实际用途后已经顺带没有带过去，不用再处理。
9. **新建 UI 子目录时不要叫 `pages`**：这个名字被 Streamlit 保留给它自己的多页面应用自动发现机制，撞了会在侧边栏冒出一份多余的导航列表。SigScout 目前用 `ui/views/` 存放页面渲染模块。

## 文档地图

- 要改需求/边界 → [REQUIREMENTS.md](REQUIREMENTS.md)
- 要查当前代码结构 → [ARCHITECTURE.md](ARCHITECTURE.md)
- 要查"为什么会变成这样" → [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md)
- 要执行拆分重构 → [EXECUTION_PLAN.md](EXECUTION_PLAN.md)
- 面向用户的功能介绍 → 根目录 `README.md`/`README.en.md`（注意脱敏边界）
- 旧的单文件交接笔记（已停用，指向本目录） → 根目录 `HANDOFF.md`（本地不提交）
