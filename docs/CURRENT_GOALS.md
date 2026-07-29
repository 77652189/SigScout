# SigScout 当前目标

维护说明：这是**变化最快**的一份文档，只保留"现在在哪、下一步做什么、有什么会绊人的坑"，不重复其他 4 份文档的内容——细节请点链接过去。每次开始一段新的工作前先看这份文档，做完一件事随手更新，不要让它跟实际进度脱节（这份文档本身过时，就是它想防止的那种"坑"）。

## 现在在哪（截至 2026-07-29）

- 湿实验反馈闭环功能已合并并推送到 `origin/master`（`c8e2d3b`），README 双语已补充说明（`a4f68a3`），需求/架构/架构变更/执行计划/当前目标 5 份工程文档已建立并推送（`02e3756`）。
- **[EXECUTION_PLAN.md](EXECUTION_PLAN.md) 里的全部 6 个 Phase（0/4/3/2/1/5）已于 2026-07-29 完成。拆分重构计划到此结束**，这份文档现在转为"日常维护 + 已知坑"清单，不再有排队等待执行的 Phase。
- **Phase 1（拆 `ui/streamlit_app.py`）**：1826 → **60 行**。新增 `ui/_shared.py`（375 行，跨页面共用）和 `ui/views/{screening,representatives,fusion_localization,experimental_feedback}.py` 四个页面文件。执行时踩到一个新类型的坑：新目录本来想按计划叫 `ui/pages/`，实际建出来后被 Streamlit 自己的多页面应用功能误认成页面目录，自动在侧边栏加了一份多余的导航列表——这个问题只有真正启动 `streamlit run` 才暴露，`pytest`/`compileall` 都测不出来。已改名为 `ui/views/` 解决。手动过了一遍全部 4 个导航项、10 个子页（含数据量最大的"OPN 实验视图"和"导入 DeepLoc 结果"），和 Phase 1 之前的基线逐项比对一致，控制台零报错——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 1。
- **Phase 5（`services/__init__.py` 导入契约）**：选定方案 B——放弃 `__init__.py` 精选重导出层。全仓库 grep 确认零消费者依赖包级 `sigscout.services` 导入后，把 49 行的重导出列表替换成一份 6 行说明性注释；不需要改任何调用方代码。`compileall`/`pytest`（53/53）/`sigscout.cli --help`/手动 Streamlit 冒烟测试全部确认无回归——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 5。
- 六个 Phase 期间 `python -m pytest -q` 全程 53/53 通过，没有新增测试（重构不改变行为，本来就不需要新测试；唯一的测试覆盖缺口仍是 UI 层，见下方"已知的坑"）。
- **UX 改善计划启动（2026-07-29）**：代码重构结束后做了一次全局复盘——功能上已对齐 [REQUIREMENTS.md](REQUIREMENTS.md) 全部 10 项能力，判定"功能已足够完善"；用户据此定下下一阶段目标：易用性/UI 布局/学习成本。计划分三步：A 低风险清理 → B 信息层次重设计 → C 导航/引导重设计，一步一步做，每步都等明确同意再继续。计划全文见 `.claude/plans/merry-forging-aurora.md`（本地，未纳入 git）。
- **Phase A 已完成（2026-07-29）**：(1) 去掉 4 处暴露给用户的本地绝对路径（`screening.py`/`fusion_localization.py`×2/`experimental_feedback.py`）；(2) 融合构建里几个"同批次所有构建共用、和候选无关"的字段（`processing_site_note`、`has_er_retention_motif`、`b_ends_with_kex2_site`、`b_pre_region_like`、`processing_quality`）之前被当成每行/每卡片都重复展示（422 个构建卡片各展示一遍完全相同的文字），现在改成生成/导入结果后只展示一次的汇总说明，两个预览表也去掉了这几列；(3) 统一了几处不一致的措辞（"相似组"→"相似分组"、"代表候选"→"代表序列"、实验状态 untested/measured/result_missing 各自 2-4 种不同标签→每个状态一个标准标签）。`compileall`/`pytest`（53/53）全绿，手动过了一遍受影响的页面（筛选页、融合定位两个子页、代表序列候选浏览、OPN 实验视图），确认路径不再出现、汇总说明正确按批次去重展示、术语统一生效，没有信息丢失。

## 下一步

1. **UX 计划 Phase B（信息层次重设计）待你确认后开始**：候选卡片/构建卡片把次要诊断细节收进 `st.expander`，只保留一个明确的头部结论；筛选页 7 个指标按漏斗顺序分组；简化 `_render_pagination_controls` 的 7 个控件。细节见 `.claude/plans/merry-forging-aurora.md` Phase B。
2. **五个 Phase 一致的教训**：写执行计划时凭经验列出的清单，动手前必须用代码里的真实依赖关系（以及目标框架的实际运行行为，Phase 1 才发现这一层）去核实，不能直接当真——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) 开头的"跨 Phase 通用教训"。
3. **顺带发现、还没处理的可选清理项**（都不在已完成 Phase 的范围内，只是顺带记录）：
   - `screening.py` 里现在最长的方法是 `annotate_persisted_source_proteins`（74 行）。
   - `ui/views/representatives.py` 里的 `_render_representative_table`/`_render_representative_workbench` 两个函数疑似死代码（in-degree 0，`main()` 可达调用链用不到），Phase 1 只做纯搬移没有删代码，原样保留，删不删需要你决定。
   - 实验反馈闭环的单目标硬编码（见下方"已知的坑"第 2 条）——如果近期要接第二个目标蛋白的湿实验数据，这个需要先解决。这条明确不在 UX 计划范围内（驱动原因是多目标就绪度，不是易用性）。
4. **如果代码库继续增长、又出现新的过大文件/耦合问题**：参照 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) 的方法论（先用 codebase-memory-mcp 的真实调用图摸底，再动手拆分、每步验证）重新走一遍流程，不需要照搬这次的具体 Phase 编号。

## 已知的坑（写代码/改文档前先看一眼）

1. **README 脱敏边界**：改 `README.md`/`README.en.md`（以及本 `docs/` 目录下这 5 份文档）之前，先确认改动里没有具体目标蛋白名称、UniProt accession 或点名该蛋白的文献引用。这条规则已经被违反过一次（2026-07-28 推送前发现），也在这次写 `docs/` 时差点又违反一次。详见 [REQUIREMENTS.md](REQUIREMENTS.md) 第 5 节。
2. **实验反馈闭环是单目标硬编码的**：`opn_measurements.csv` 路径、`target_key="opn"`（现在分散在 `ui/views/experimental_feedback.py`/`ui/views/fusion_localization.py` 里）、`render_opn_experimental_browser`、`fusion_selected_candidate_ids_opn` 这些都还没跟着 `FUSION_TARGET_PRESETS` 多目标化。现在只有一个目标在用，暂时不会炸；一旦要接第二个目标蛋白的湿实验数据，这里必须先改。详见 [ARCHITECTURE.md](ARCHITECTURE.md) 第 4 节。
3. **UI 层零自动化测试**：`ui/streamlit_app.py`、`ui/_shared.py`、`ui/views/*.py`、`ui/experimental_browser.py` 没有任何 pytest 覆盖，Phase 1 拆分后依然如此。改 UI 之后 `pytest -q` 全绿不代表没坏，必须手动跑一遍 Streamlit 页面。
4. **`services/__init__.py` 现在是刻意留空的**（Phase 5 已解决，方案 B）：不要从 `sigscout.services` 包级导入任何东西，也不要往 `__init__.py` 里加"精选重导出"——统一直接从具体子模块 import（例如 `from sigscout.services.screening import SignalPeptideScreeningService`）。
5. **没有 `.gitattributes`，行尾风格依赖每台机器的 `core.autocrlf` 设置**（本机是 `true`）：这是为什么这次会话里几乎每条涉及文件改动的 git 命令都弹 "LF will be replaced by CRLF" 警告。目前不影响功能，但换一台 `autocrlf=false` 的机器协作时可能出现整份文件的行尾 diff 噪音。如果以后要多人协作，值得补一个 `.gitattributes` 固定 `* text=auto`。
6. **`core/paths.py` 的 `opn_saved_screening_dir` 属性名残留**：命名没跟上多目标化，见 [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md) 2026-06-18 条目。低优先级，顺手改的时候改。
7. **一个跟 Phase 0 无关的死 import**（执行 Phase 0 时顺带发现）：`services/source_protein_annotation.py` 的 `from typing import Iterable` 目前没有实际用到，低优先级，顺手清理即可。原来 `streamlit_app.py` 里还有一个未使用的 `annotate_candidate_experimental_evidence` 导入，Phase 1 重写 `ui/views/fusion_localization.py` 时核对每个 import 的实际用途后已经顺带没有带过去，不用再处理。
8. **新建 UI 子目录时不要叫 `pages`**：这个名字被 Streamlit 保留给它自己的多页面应用自动发现机制，撞了会在侧边栏冒出一份多余的导航列表。SigScout 目前用 `ui/views/` 存放页面渲染模块。

## 文档地图

- 要改需求/边界 → [REQUIREMENTS.md](REQUIREMENTS.md)
- 要查当前代码结构 → [ARCHITECTURE.md](ARCHITECTURE.md)
- 要查"为什么会变成这样" → [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md)
- 要执行拆分重构 → [EXECUTION_PLAN.md](EXECUTION_PLAN.md)
- 面向用户的功能介绍 → 根目录 `README.md`/`README.en.md`（注意脱敏边界）
- 旧的单文件交接笔记（已停用，指向本目录） → 根目录 `HANDOFF.md`（本地不提交）
