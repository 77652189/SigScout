# SigScout

[English README](README.en.md)

SigScout 是一个面向分泌表达设计的信号肽工作台，用于发现、解释、筛选、聚类和导出候选信号肽。当前默认流程聚焦于从毕赤酵母/Komagataella 来源蛋白中整理可用于异源分泌表达讨论的信号肽候选。

SigScout 的目标不是替代湿实验，而是把首轮候选整理成可审查、可讨论、可复现的实验草案：保留来源证据，透明展示规则判断，折叠高度相似序列，并导出 CSV/FASTA 供后续实验设计或 DNA/CDS 层工具使用。

## 功能

- 从 UniProt 获取带 `signal peptide` 注释的候选序列。
- 用透明规则检查信号肽三段结构：N 区正电、H 区疏水核心、C 区切割位点。
- 可选调用 USPNet-fast 做机器学习复核；未安装时不会阻断规则筛选。
- 将来源蛋白定位辅助评估作为独立步骤执行；刷新候选不会自动给出分泌/膜/未知分类。
- 来源蛋白评估基于 UniProt 受控 subcellular location、GO cellular component、feature evidence code，并可选查询 QuickGO/GOA 证据；不依赖自由文本关键词命中。
- 对高度相似的信号肽分组，默认展示代表序列，同时保留完整候选和重复证据。
- 导出 CSV、FASTA 和 JSON summary，便于首轮湿实验讨论或下游密码子优化。
- 支持从本地已保存结果加载页面展示；实验上下文和示例筛选输出默认不进入 Git。

## 边界

SigScout 不做 pcSec 模型比较，不依赖 MATLAB，不做密码子优化，也不集成 SignalP 6.0。PichiaCLM 等工具可以作为后续 DNA/CDS 设计工具读取 SigScout 导出的代表序列，但 SigScout 本身只负责蛋白层候选筛选。

SigScout 输出的是实验讨论版候选，不是最终可下单合成序列。真实表达效果必须由具体菌株、载体、培养条件和湿实验验证。

## 安装

建议使用 Python 3.10 或更高版本。

```powershell
cd C:\Users\63097\Documents\CursorProject\SigScout
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[test]"
```

## 启动

推荐端口是 `8506`：

```powershell
python -m streamlit run src/sigscout/ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8506
```

也可以使用 CLI：

```powershell
python -m sigscout.cli serve --port 8506
python -m sigscout.cli discover --taxon-id 4922 --max-records 300
python -m sigscout.cli screen --taxon-id 4922 --max-records 300
python -m sigscout.cli annotate-source --quickgo
```

## 输入和输出

主要输入：

- 候选信号肽来源，例如 UniProt、文献、手动导入或内部实验记录。
- UniProt 检索条件，例如 taxon ID、最大记录数和 reviewed-only 选项。

标准输出：

- `uniprot_candidates.csv`
- `uniprot_duplicate_candidates.csv`
- `signal_peptide_method_comparison.csv`
- `signal_peptide_representatives.csv`
- `method_recommended_candidates.fasta`
- `method_representative_candidates.fasta`
- `signal_peptide_method_comparison_summary.json`

代表序列页面还可以基于 A=候选信号肽、B=固定辅助序列、C=目标蛋白生成 `AC` / `ABC` 融合蛋白 FASTA 和构建索引 CSV，并加入 `C_ONLY`、`BC` 与可选阳性 leader 对照。构建表会补充 Kex2/Ste13、ER retention motif、液泡/膜定位风险、内部疏水段等辅助扫描，并输出信号肽质量、加工质量、外部定位支持、设计风险和综合优先级。DeepLoc 2.1 或 BUSCA 结果建议手动上传到对应网页服务后，再把 CSV/TSV 结果导入 SigScout 合并展示；SigScout 不自动调用这些网页服务。

来源蛋白辅助评估会在 CSV 中补充 `source_protein_route`、`source_protein_evidence_level`、`source_protein_route_basis`、UniProt 结构化证据 JSON 和可选 QuickGO/GOA 证据。辅助结论只用于排序和人工审查，不作为自动删除候选的条件。

本地真实运行结果默认写入 `local_runs/`，该目录已被 `.gitignore` 忽略。实验交接上下文 `HANDOFF.md`、示例筛选输出 `examples/opn/saved_screening/`、Python 缓存、pytest 缓存、coverage、打包产物、Streamlit 本地配置和知识图谱分析缓存也不会进入 Git。

## 项目结构

```text
src/sigscout/core/          领域模型、路径解析、输入接口
src/sigscout/adapters/      UniProt、USPNet、本地进程适配器
src/sigscout/services/      候选库、规则筛选、聚类、导出和输入实现
src/sigscout/ui/            Streamlit 工作台
tests/                      单元测试
```

## 开发验证

```powershell
python -m compileall src tests sigscout
python -m pytest -q
python -m sigscout.cli --help
```

Streamlit 健康检查：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8506/_stcore/health
```

## 合规说明

- UniProt 数据作为公开数据库来源使用，仍需在对外材料中保留 accession、来源数据库、检索条件和查询日期。
- QuickGO/GOA 证据来自 EMBL-EBI 服务；用于辅助审查时应保留 GO ID、evidence code、reference 和查询日期。
- USPNet-fast 是可选外部复核工具；使用模型文件和代码时请遵守其官方仓库许可证与模型获取说明。
- 如果本地启用 USPNet-fast，建议放在 `external/USPNet/`；该目录已被 Git 忽略。也可以用 `USPNET_REPO` / `USPNET_MODEL_DIR` 指向其它本地位置。
- SignalP 6.0 涉及官方许可和使用限制，本项目不下载、不集成、不作为默认路线。
- 本工具不对表达量、分泌效率或最终构建表现作保证。

## 致谢

SigScout 使用并感谢以下开源项目和数据来源：

- [UniProt](https://www.uniprot.org/)：提供蛋白序列、signal peptide 注释和 accession 来源信息。
- [QuickGO / GOA](https://www.ebi.ac.uk/QuickGO/)：提供 GO cellular component 注释、evidence code 和参考来源。
- [USPNet](https://github.com/ml4bio/USPNet)：作为可选的机器学习信号肽复核工具。
- [Streamlit](https://streamlit.io/)：用于构建交互式本地工作台。
- [pandas](https://pandas.pydata.org/)：用于 CSV 读写和表格处理。
- [Pydantic](https://docs.pydantic.dev/)：用于候选记录的数据建模。
- [pytest](https://pytest.org/)：用于项目测试。

## 许可证

当前仓库尚未声明开源许可证。对外复用、发布或商业分发前，请先补充明确许可证并复核第三方数据和模型的使用条款。
