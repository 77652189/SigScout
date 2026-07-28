# SigScout 需求文档

维护说明：这份文档描述"SigScout 应该做什么、不应该做什么"，是相对稳定的内容。当前正在做什么、下一步做什么，见 [CURRENT_GOALS.md](CURRENT_GOALS.md)；架构如何实现这些需求，见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 1. 定位

SigScout 是蛋白层面的信号肽筛选与融合构建工作台，服务于分泌表达目标蛋白的候选信号肽发现、解释、聚类和导出。

它不预测真实分泌效率，而是在湿实验前把候选范围收窄到一批可讨论、可审查、可复现的序列，为后续密码子优化、融合构建和定位风险评估准备结构化输入。

## 2. 功能性需求

| 能力 | 说明 |
|---|---|
| 候选发现 | 从 UniProt 按 `organism_id AND ft_signal:*` 拉取带 `signal peptide` 注释的候选；支持本地 CSV 候选导入 |
| 重复检测 | 完全相同信号肽序列单独记录为重复证据，不删除、不覆盖原始候选 |
| 规则评分 | 显式检查 N 区正电、H 区疏水核心、C 区切割位点偏好、低复杂度风险；规则必须可解释（每条候选能说清楚为什么通过/未通过） |
| USPNet 复核 | 可选调用本地 USPNet-fast；本机未安装时不能阻断或崩溃规则筛选流程 |
| 来源蛋白证据 | 基于 UniProt 结构化定位、GO cellular component、feature evidence code，以及可选 QuickGO/GOA 证据，判断来源蛋白的分泌/膜锚定倾向路线；规则来自可维护的 `data/source_protein_route_map.json`，不能硬编码在代码里 |
| 相似序列聚类 | 对高度相似的信号肽分组，只用代表序列做首轮讨论/下载，但必须保留完整候选列表和重复证据，不能因为聚类丢信息 |
| 融合构建 | 支持多个目标蛋白预设之间切换，生成 AC / ABC 融合蛋白序列、构建索引、阳性引导肽对照、基础加工风险扫描 |
| 定位结果导入 | 导入 DeepLoc 2.1 或 BUSCA 的 CSV/TSV 结果，合并进构建排序表；不自动调用这些外部网页工具 |
| 实验反馈闭环 | 导入湿实验测量结果 CSV，按精确序列匹配回候选/构建；基于已测数据生成下一轮引导探索候选面板（覆盖正向邻域、通用预测强、多样性保留、低表现对照四类需求，不能只推荐"看起来最好"的一种） |
| 导出 | 输出 CSV、FASTA、JSON 摘要，供实验讨论或下游工具（如 PichiaCLM）衔接 |
| CLI | `discover` / `screen` / `annotate-source` / `serve` 四个子命令，可脚本化运行，不依赖必须打开网页 |

## 3. 明确的非目标（Non-goals）

这些是有意为之的边界，不是尚未实现的功能：

- **不做真实分泌效率预测**：输出是候选优先级讨论集合，不是可直接合成的最终保证；真实分泌表现必须在实际菌株、载体、培养条件和检测方法中验证。
- **不跑 pcSec 模型比较**：不依赖 MATLAB，不调用 pcSecYeastSpecies 的 pcSecPichia 模型。
- **不做密码子优化**：DNA/CDS 层优化是 PichiaCLM 的职责，不在 SigScout 内实现。
- **不集成/下载 SignalP 6.0**：涉及官方许可和商业使用限制，不能把相关安装包、模型权重提交进仓库或在代码里静默下载。
- **不自动调用 DeepLoc/BUSCA**：需要用户手动在网页端跑完，导出 CSV/TSV 后手动导入 SigScout。
- **实验反馈不跨目标外推**：某个目标蛋白的湿实验结果只影响该目标自己的候选排序和引导探索，不改写通用候选分数，也不代表统计显著性——这是分层排序规则，不是绝对产量比较。

## 4. 与相邻项目的职责边界

三个项目分工明确，不能互相越界重新实现对方职责：

- **SigScout**：蛋白层信号肽候选筛选、融合构建、湿实验反馈闭环。
- **PichiaCLM**：DNA/CDS 层密码子优化，消费 SigScout 导出的代表序列。
- **pcSecYeastSpecies**：MATLAB/pcSec 模型浏览和仿真；已保留对应目标蛋白的模型输入接口（模块路径见该项目内部文档），只负责把"目标蛋白成熟序列 + leader 候选"转成 pcSecPichia 能读的输入，不负责信号肽筛选。

如果要接入新的预测方法，放在 `src/sigscout/adapters/`，由 `services/screening.py` 编排，不要写进 UI 层。如果要接入新的候选输入来源（网页上传、内部实验表格等），优先新增一个 `CandidateInputProvider`/`TargetProteinInputProvider` 实现，不要让 Streamlit 页面直接解析业务输入。

## 5. 文档与信息披露要求

- **`README.md` / `README.en.md` 禁止出现具体目标蛋白的名称、俗名或全称**、其 UniProt accession，或点名该蛋白的文献引用，即使代码/测试/数据文件中已经使用了真实名称。用"目标蛋白"/"target protein" 等通用说法替代。这是与 pcSecYeastSpecies 一致的保密边界（详见 commit `3be1de2`），不是遗漏。
- 本 `docs/` 目录下的 5 份工程文档纳入 git 提交，同样需要遵守上一条边界（不写具体目标蛋白名称）。
- 外部材料中引用 UniProt 数据需保留 accession、查询条件、数据库来源和查询日期；引用 QuickGO/GOA 证据需保留 GO ID、证据代码、参考文献和查询日期；导入湿实验反馈需保留批次、检测方法和测量日期。
- 运行输出（`local_runs/`）、外部工具（`external/USPNet/`）、商业受限资源（SignalP 安装包、模型权重）不提交进仓库。

## 6. 验收/验证方式

- `python -m pytest -q`：现有单元测试覆盖 `services/`、`adapters/`、`core/`；**UI 层（`ui/streamlit_app.py`、`ui/experimental_browser.py`）目前没有自动化测试**，新增/修改 UI 需要手动跑一遍 Streamlit 页面验证。
- `python -m compileall src tests sigscout`：语法/导入层面的快速检查。
- `python -m sigscout.cli --help`：确认 CLI 入口未被破坏。
- Streamlit 健康检查：`Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8506/_stcore/health`。
