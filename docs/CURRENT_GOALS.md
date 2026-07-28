# SigScout 当前目标

维护说明：这是**变化最快**的一份文档，只保留"现在在哪、下一步做什么、有什么会绊人的坑"，不重复其他 4 份文档的内容——细节请点链接过去。每次开始一段新的工作前先看这份文档，做完一件事随手更新，不要让它跟实际进度脱节（这份文档本身过时，就是它想防止的那种"坑"）。

## 现在在哪（截至 2026-07-28，commit `a4f68a3`）

- 湿实验反馈闭环功能已合并并推送到 `origin/master`（`c8e2d3b`），README 双语已补充说明（`a4f68a3`）。
- 针对过大文件/重复代码做了一次量化审计，产出了 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) 的分阶段拆分方案，**尚未开始执行任何一个 Phase**。
- 需求/架构/架构变更/执行计划/当前目标 5 份工程文档（也就是本文档所在的 `docs/` 目录）刚建立，纳入 git 提交。

## 下一步（等待决定，不要自己默认选一个就动手）

1. **要不要现在就开始执行 [EXECUTION_PLAN.md](EXECUTION_PLAN.md)？** 如果要，按文档里的推荐顺序从 Phase 0（去重）开始，风险最低。
2. **Phase 5 的开放决策**（`services/__init__.py` 到底该不该是唯一导入入口，方案 A/B）需要先定方向，否则 Phase 1-4 拆完之后 import 路径可能要再改一遍。
3. 如果暂时不做拆分，继续功能开发时，至少留意下面"新功能会撞到的坑"里的第 1、4 条。

## 已知的坑（写代码/改文档前先看一眼）

1. **README 脱敏边界**：改 `README.md`/`README.en.md`（以及本 `docs/` 目录下这 5 份文档）之前，先确认改动里没有具体目标蛋白名称、UniProt accession 或点名该蛋白的文献引用。这条规则已经被违反过一次（2026-07-28 推送前发现），也在这次写 `docs/` 时差点又违反一次。详见 [REQUIREMENTS.md](REQUIREMENTS.md) 第 5 节。
2. **实验反馈闭环是单目标硬编码的**：`opn_measurements.csv` 路径、`target_key="opn"`、`render_opn_experimental_browser`、`fusion_selected_candidate_ids_opn` 这些都还没跟着 `FUSION_TARGET_PRESETS` 多目标化。现在只有一个目标在用，暂时不会炸；一旦要接第二个目标蛄白的湿实验数据，这里必须先改。详见 [ARCHITECTURE.md](ARCHITECTURE.md) 第 4 节。
3. **UI 层零自动化测试**：`ui/streamlit_app.py`、`ui/experimental_browser.py` 没有任何 pytest 覆盖。改 UI 之后 `pytest -q` 全绿不代表没坏，必须手动跑一遍 Streamlit 页面。执行 Phase 1 拆分时这一条风险会被放大，见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md) Phase 1。
4. **`services/__init__.py` 的 `__all__` 已经和实际用法脱节**：不要假设它是当前的"唯一入口"——`streamlit_app.py`、`experimental_browser.py` 一直在绕过它直接 import 子模块。新增导出时记得两边都检查一下，或者干脆先做 Phase 5 的决策。
5. **仓库根目录有一个未纳入版本控制的 `external.7z`**：不清楚是什么内容、要不要长期保留在工作目录里。如果确认不需要提交，建议加进 `.gitignore` 或直接清理，避免以后有人误以为它该被提交、或者不知道能不能删。**这个由你决定，我没有主动处理。**
6. **没有 `.gitattributes`，行尾风格依赖每台机器的 `core.autocrlf` 设置**（本机是 `true`）：这是为什么这次会话里几乎每条涉及文件改动的 git 命令都弹 "LF will be replaced by CRLF" 警告。目前不影响功能，但换一台 `autocrlf=false` 的机器协作时可能出现整份文件的行尾 diff 噪音。如果以后要多人协作，值得补一个 `.gitattributes` 固定 `* text=auto`。
7. **`core/paths.py` 的 `opn_saved_screening_dir` 属性名残留**：命名没跟上多目标化，见 [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md) 2026-06-18 条目。低优先级，顺手改的时候改。

## 文档地图

- 要改需求/边界 → [REQUIREMENTS.md](REQUIREMENTS.md)
- 要查当前代码结构 → [ARCHITECTURE.md](ARCHITECTURE.md)
- 要查"为什么会变成这样" → [ARCHITECTURE_CHANGES.md](ARCHITECTURE_CHANGES.md)
- 要执行拆分重构 → [EXECUTION_PLAN.md](EXECUTION_PLAN.md)
- 面向用户的功能介绍 → 根目录 `README.md`/`README.en.md`（注意脱敏边界）
- 旧的单文件交接笔记（已停用，指向本目录） → 根目录 `HANDOFF.md`（本地不提交）
