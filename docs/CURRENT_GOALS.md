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
- **Phase B 已完成（2026-07-29）**：(1) 候选卡片（`representatives.py`）把"依据说明"证据文本和 N区/H区 mini-grid 收进折叠的 `st.expander("评分细节与依据说明")`，头条只留路线徽章/证据徽章/规则分数条；(2) 融合构建卡片（`fusion_localization.py`）把 Phase A 后剩下的 4 格 mini-grid（定位概率分/A细节分/来源证据/膜液泡风险）收进 `st.expander("评分细节")`，4 个 `st.metric` 头条不变；(3) 筛选页 7 个指标（`screening.py`）从一行铺开改成三段漏斗分组：候选发现与去重 → 规则/USPNet 打分复核 → 相似聚类与代表序列；(4) 分页控件（`_shared.py:_render_pagination_controls`）把"跳转页"输入框和单独的"跳转"按钮合并成一个 `on_change` 触发的 number_input，从 7 个控件减到 6 个（原计划写的是"减到 5 个"，实际去掉"跳转"按钮这一个后是 6 个——"第一页/最后一页"两个快捷按钮翻页多时仍有用，没有一并去掉，执行时判断不值得为了凑数字牺牲功能）。`compileall`/`pytest`（53/53）全绿，手动展开验证了候选卡片和构建卡片的折叠区，确认里面的数值/文本和折叠前完全一致，没有信息丢失。
- **Phase C 已完成（2026-07-29）——UX 改善计划三步全部做完**：(1) `ui/streamlit_app.py:main()` 里手写的两级 `st.sidebar.radio` + if/elif 分发换成了 Streamlit 原生 `st.navigation`/`st.Page`，侧边栏现在是 4 个带标题的分组、10 个带图标的子页面（不再是纯文字单选按钮）；(2) 因为 `st.Page` 的 callable 不能带参数，4 个 view 模块各自新增了一组无参数的 `page_*` 包装函数（内部固定传参调用原来的 `render_*(subpage)`），原有渲染逻辑本身没有重构；(3) 顺手把硬编码的"OPN 实验结果"顶层导航标签泛化成"实验结果"（只改标签，没动 `target_key="opn"` 等底层单目标数据管线，那仍然是已知的坑，见下方第 2 条）；(4) 在筛选页（默认落地页）加了一个可折叠、默认展开的首次使用引导（`st.expander`），讲清楚"筛选→代表序列→融合定位→实验反馈"四步流水线，点"知道了，不再提示"后记进 `st.session_state["onboarding_dismissed"]`，不会再弹出。改动前后各做了一遍完整的 10 个子页面人工点击走查（和拆 `ui/pages/` 时同样的规矩），逐项核对内容/数字/折叠区一致，`compileall`/`pytest`（53/53）全绿。**这是 UX 改善计划的最后一步，A/B/C 三步现在全部完成**。
- **可选清理项收尾（2026-07-29）**：把之前"顺带发现、低优先级"的几条坑逐一重新核实并处理掉：(1) 删除 `services/source_protein_annotation.py` 未使用的 `from typing import Iterable`；(2) 重新 grep 确认 `ui/views/representatives.py` 的 `_render_representative_table`/`_render_representative_workbench` 全代码库零引用后删除；(3) `screening.py` 原本 74 行的 `annotate_persisted_source_proteins` 仿照 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 2 的模式拆成 4 个私有步骤方法（`_load_persisted_rows_for_annotation`/`_collect_quickgo_annotations`/`_annotate_persisted_csv_files`/`_finalize_source_protein_annotation`），本体缩到 13 行，最长子方法 32 行，纯结构重组、`tests/test_screening.py` 现有 8 个测试原样通过，另外手动触发了一次真实的"评估来源蛋白定位"点击，确认评估时间戳/统计数字正确刷新；(4) 新增 `.gitattributes`（`* text=auto`）；(5) `core/paths.py` 的 `opn_saved_screening_dir` 属性改名为 `example_saved_screening_dir`——只改 Python 属性标识符，返回的实际磁盘路径 `examples/opn/saved_screening` 没有变，这是本来就存在的示例数据目录，不做文件移动。**评估过、判断不适合当"顺手清理"处理，需要你决定要不要单独立项**：实验反馈闭环单目标硬编码、UI 层零自动化测试——这两条本质上是需要设计决策的功能性/架构性工作（前者要决定"第二个目标接入时数据管线怎么参数化"，后者要决定测试框架和覆盖范围），不是单纯的代码清理，见下方"已知的坑"第 2、3 条的更新说明。全部改动用 `review-fix-loop` 走了一遍代码审查，没有发现问题；`compileall`/`pytest`（53/53）全绿。
- **补一条：姊妹属性也改完了（2026-07-29）**：上面顺带发现的 `opn_screening_output_dir`（`local_runs/opn_signal_peptides`，5 处引用）按你的要求也改名为 `screening_output_dir` 了，同样只改属性标识符不动实际磁盘路径。手动验证了主筛选服务（`cli.py`/`ui/_shared.py` 用的路径）和融合定位的 DeepLoc 缓存查找（`fusion_localization.py` 用的路径）都还能正确工作——"导入 DeepLoc 结果"页面依然正确展示 424 条缓存结果。`opn_*` 命名残留这条坑现在彻底清空了。
- **UI 层补上了基本冒烟测试（2026-07-29）**：新增 `tests/test_ui_smoke.py`，用 Streamlit 自带的 `AppTest` 框架（不开浏览器）给 10 个页面各配一个测试，断言渲染无异常、确实有内容，外加一个用 `monkeypatch` 模拟"全新 checkout、没有本地数据"场景的测试，确认几个关键页面走的是已有的优雅降级分支而不是报错。踩了一个不直观的坑：`AppTest.from_function` 要求传入的函数必须"自包含"（会把函数源码单独提取执行，脱离原模块的 import 上下文），不能直接传 `page_screening` 这类定义在 view 模块里、内部引用同模块其他名字的函数（会 `NameError`），每个页面配了一个只做"函数内 import + 调用"的薄包装函数解决。`pytest -q` 现在是 64/64（新增 11 个）。**这仍然只是页面级冒烟，不是全面覆盖**——不模拟按钮点击/表单交互、不断言具体数值，改 UI 之后手动 Streamlit 走查依然必要，见下方已知的坑第 3 条的更新说明。

## 下一步

没有排队中的 UX Phase 了（A/B/C 三步都做完，见上方记录），可选清理项也已收尾。剩下的都是需要你做决策才能推进的项目：

1. **实验反馈闭环单目标硬编码**（见下方"已知的坑"第 2 条）——如果近期要接第二个目标蛋白的湿实验数据，需要先把这个解决；不接的话可以一直放着，不影响现有功能。
2. **如果想让 UI 测试覆盖更深**（见下方"已知的坑"第 3 条）：现在只有页面级冒烟（渲染不报错），想再往下做的话是模拟具体交互（点按钮、切筛选条件、翻页等），用 `AppTest` 已有的 `at.button[i].click().run()` 这类 API 应该能做，但这是新的一块工作量，不是这次顺手就做的范围。
3. **六个代码重构 Phase + 三个 UX Phase 一致的教训**：写执行计划时凭经验列出的清单，动手前必须用代码里的真实依赖关系（以及目标框架/库的实际运行行为——代码重构 Phase 1 的 `ui/pages/` 命名冲突、UX 计划里 `st.Page` 不能带参数、这次 `AppTest.from_function` 要求自包含函数，都是这么发现的）去核实，不能直接当真——细节见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) 开头的"跨 Phase 通用教训"。
4. **如果代码库继续增长、又出现新的过大文件/耦合问题，或者想再做一轮 UX 打磨**：参照 [EXECUTION_PLAN.md](EXECUTION_PLAN.md)/`.claude/plans/merry-forging-aurora.md` 的方法论（先摸底找具体问题、写清楚的分阶段计划、一步一步做、每步都验证）重新走一遍流程，不需要照搬这次的具体 Phase 编号。

## 已知的坑（写代码/改文档前先看一眼）

1. **README 脱敏边界**：改 `README.md`/`README.en.md`（以及本 `docs/` 目录下这 5 份文档）之前，先确认改动里没有具体目标蛋白名称、UniProt accession 或点名该蛋白的文献引用。这条规则已经被违反过一次（2026-07-28 推送前发现），也在这次写 `docs/` 时差点又违反一次。详见 [REQUIREMENTS.md](REQUIREMENTS.md) 第 5 节。
2. **实验反馈闭环是单目标硬编码的**：`opn_measurements.csv` 路径、`target_key="opn"`（现在分散在 `ui/views/experimental_feedback.py`/`ui/views/fusion_localization.py` 里）、`render_opn_experimental_browser`、`fusion_selected_candidate_ids_opn` 这些都还没跟着 `FUSION_TARGET_PRESETS` 多目标化。现在只有一个目标在用，暂时不会炸；一旦要接第二个目标蛋白的湿实验数据，这里必须先改。**2026-07-29 评估过**：这不是简单的改名/清理，而是要决定"怎么把路径/键名按目标参数化"这个设计问题，所以没有跟着这次的可选清理项一起动，仍然记录在这里等你决定。详见 [ARCHITECTURE.md](ARCHITECTURE.md) 第 4 节。
3. **UI 层测试覆盖仍然很薄**：`tests/test_ui_smoke.py`（2026-07-29 新增）用 `streamlit.testing.v1.AppTest` 给 10 个页面做了冒烟测试（渲染不报错 + 确实有内容 + 无本地数据时优雅降级），但不模拟点击/表单交互、不断言具体展示的数值。改 UI 之后 `pytest -q` 全绿仍然不代表没坏（比如 Phase 1 的 `ui/pages/` 命名冲突这种运行时行为问题，冒烟测试也测不出来），手动跑一遍 Streamlit 页面依然是改动后的必要步骤。
4. **`services/__init__.py` 现在是刻意留空的**（Phase 5 已解决，方案 B）：不要从 `sigscout.services` 包级导入任何东西，也不要往 `__init__.py` 里加"精选重导出"——统一直接从具体子模块 import（例如 `from sigscout.services.screening import SignalPeptideScreeningService`）。
5. **新建 UI 子目录时不要叫 `pages`**：这个名字被 Streamlit 保留给它自己的多页面应用自动发现机制，撞了会在侧边栏冒出一份多余的导航列表。SigScout 目前用 `ui/views/` 存放页面渲染模块。

## 文档地图

- 要改需求/边界 → [REQUIREMENTS.md](REQUIREMENTS.md)
- 要查当前代码结构 → [ARCHITECTURE.md](ARCHITECTURE.md)
- 要查"为什么会变成这样" → [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md)
- 要执行拆分重构 → [EXECUTION_PLAN.md](EXECUTION_PLAN.md)
- 面向用户的功能介绍 → 根目录 `README.md`/`README.en.md`（注意脱敏边界）
- 旧的单文件交接笔记（已停用，指向本目录） → 根目录 `HANDOFF.md`（本地不提交）
