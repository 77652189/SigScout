from __future__ import annotations

from sigscout.core.models import SignalPeptideCandidate
from sigscout.services.library import SignalPeptideLibraryService


DEFAULT_TAXON_ID = 4922
OPN_SHORTLIST = ("OPN_PPA_PASCHR3_0030", "OPN_PPA_DDDK18", "OPN_ALPHA_FULL_PROJECT")

MATURE_OPN = (
    "IPVKQADSGSSEEKQLYNKYPDAVATWLNPDPSQKQNLLAPQNAVSSEETNDFKQETLPSKSNES"
    "HDHMDDMDDEDDDDHVDSQDSIDSNDSDDVDDTDDSHQSDESHHSDESDELVTDFPTDLPATEVFT"
    "PVVPTVDTYDGRGDSVVYGLRSKSKKFRRPDIQYPDATDEDITSHMESEELNGAYKAIPVAQDLN"
    "APSDWDSRGKDSYETSQLDDQSAETHSHKQSRLYKRKANDESNEHSDVIDSQELSKVSREFHSHEF"
    "HSHEDMLVVDPKSKEEDKHLKFRISHELDSASSEVN"
)

PROJECT_ALPHA_FACTOR_LEADER = (
    "MRFPSIFTAVLFAASSALAAPVNTTTEDETAQIPAEAVIGYSDLEGDFDVAVLPFSNSTNNGLLFI"
    "NTTIASIAAKEEGVSLEKREAEA"
)
PROJECT_ALPHA_FACTOR_SP = "MRFPSIFTAVLFAASSALA"
PROJECT_ALPHA_FACTOR_PRO = PROJECT_ALPHA_FACTOR_LEADER[len(PROJECT_ALPHA_FACTOR_SP) :]
HUMAN_SPP1_NATIVE_SP = "MRIAVICFCLLGITCA"
SC_OST1_N23 = "MRQVWFSWIVGLFLCFFNVSSAA"
PPA_DDDK18_SP = "MFNLKTILISTLASIAVA"
PPA_PAS_CHR3_0030_SP = "MKFAISTLLIILQAAAVFAA"
PPA_EPX1_SA_SP = "MKLSTNLILAIAAASAVVSA"


def opn_candidates() -> list[SignalPeptideCandidate]:
    return [
        SignalPeptideCandidate(
            candidate_id="OPN_ALPHA_FULL_PROJECT",
            leader_sequence=PROJECT_ALPHA_FACTOR_LEADER,
            signal_peptide_sequence=PROJECT_ALPHA_FACTOR_SP,
            category="project_baseline",
            category_label="alpha-factor 基线",
            processing_route="alpha-factor prepro; signal peptidase plus Kex2/Ste13-like pro-leader processing",
            source_note="项目当前使用的 alpha-factor leader；保留为工业常用对照。",
            rationale="作为首轮实验对照最合适，便于和常用 Pichia 分泌方案比较。",
            caution="成熟 OPN 内部有 RR/KR 二碱性位点；使用 alpha pro/Kex2 路线时需关注异常切割。",
            library_stage="首轮推荐",
            source_type="项目基线",
            construct_length=len(PROJECT_ALPHA_FACTOR_LEADER) + len(MATURE_OPN),
        ),
        SignalPeptideCandidate(
            candidate_id="OPN_ALPHA_PRE_ONLY",
            leader_sequence=PROJECT_ALPHA_FACTOR_SP,
            signal_peptide_sequence=PROJECT_ALPHA_FACTOR_SP,
            category="yeast_signal_only",
            category_label="酵母短信号肽",
            processing_route="signal peptidase only",
            source_note="alpha-factor pre 信号肽部分，不含 pro 区。",
            rationale="用于拆分 alpha pre 和 alpha pro 的影响。",
            caution="可能弱于完整 alpha-factor prepro，主要作为比较臂。",
            source_type="项目拆分",
            construct_length=len(PROJECT_ALPHA_FACTOR_SP) + len(MATURE_OPN),
        ),
        SignalPeptideCandidate(
            candidate_id="OPN_NATIVE_SPP1",
            leader_sequence=HUMAN_SPP1_NATIVE_SP,
            signal_peptide_sequence=HUMAN_SPP1_NATIVE_SP,
            category="target_native_signal",
            category_label="OPN 天然信号肽",
            processing_route="signal peptidase only",
            source_note="人 SPP1/osteopontin 天然 N 端信号肽，UniProt P10451 residues 1-16。",
            rationale="作为目标蛋白自身信号肽的生物学参考。",
            caution="哺乳动物天然信号肽不一定适合 Pichia。",
            source_type="UniProt/目标天然",
            construct_length=len(HUMAN_SPP1_NATIVE_SP) + len(MATURE_OPN),
        ),
        SignalPeptideCandidate(
            candidate_id="OPN_OST1N23_ALPHA_PRO",
            leader_sequence=SC_OST1_N23 + PROJECT_ALPHA_FACTOR_PRO,
            signal_peptide_sequence=SC_OST1_N23,
            category="hybrid_yeast_leader",
            category_label="杂合酵母 leader",
            processing_route="Ost1 N-terminal signal peptide plus alpha-factor pro region",
            source_note="S. cerevisiae OST1 N 端 pre 序列结合 alpha-factor pro 区。",
            rationale="常见 secretion-engineering 比较路线。",
            caution="仍使用 alpha pro/Kex2 加工路线，不能消除 OPN 内部二碱性位点风险。",
            source_type="文献/杂合设计",
            construct_length=len(SC_OST1_N23 + PROJECT_ALPHA_FACTOR_PRO) + len(MATURE_OPN),
        ),
        SignalPeptideCandidate(
            candidate_id="OPN_PPA_DDDK18",
            leader_sequence=PPA_DDDK18_SP,
            signal_peptide_sequence=PPA_DDDK18_SP,
            category="pichia_native_signal",
            category_label="毕赤酵母来源信号肽",
            processing_route="signal peptidase only",
            source_note="Reported Pichia DDDK 18-aa signal peptide candidate.",
            rationale="避免 alpha pro/Kex2 路线，同时保留 Pichia 相关来源。",
            caution="最终仍需在目标菌株、载体和培养条件下小试验证。",
            library_stage="首轮推荐",
            source_type="文献",
            construct_length=len(PPA_DDDK18_SP) + len(MATURE_OPN),
        ),
        SignalPeptideCandidate(
            candidate_id="OPN_PPA_PASCHR3_0030",
            leader_sequence=PPA_PAS_CHR3_0030_SP,
            signal_peptide_sequence=PPA_PAS_CHR3_0030_SP,
            category="pichia_native_signal",
            category_label="毕赤酵母来源信号肽",
            processing_route="signal peptidase only",
            source_note="Pichia pastoris PAS_chr3_0030 signal peptide reported in secretion-leader screening resources.",
            rationale="短 Pichia-native leader，适合首轮和 DDDK18、alpha-factor 对照并行比较。",
            caution="来源蛋白和工业表现可能具有产品依赖性。",
            library_stage="首轮推荐",
            source_type="文献",
            construct_length=len(PPA_PAS_CHR3_0030_SP) + len(MATURE_OPN),
        ),
        SignalPeptideCandidate(
            candidate_id="OPN_PPA_EPX1_SA",
            leader_sequence=PPA_EPX1_SA_SP,
            signal_peptide_sequence=PPA_EPX1_SA_SP,
            category="pichia_native_signal",
            category_label="毕赤酵母来源信号肽",
            processing_route="signal peptidase only",
            source_note="Pichia EPX1 signal-anchor/signal-peptide fragment reported in secretion-leader screening resources.",
            rationale="提供另一个 Pichia-native 短 leader，疏水核心组成不同。",
            caution="signal-anchor 行为可能受下游蛋白影响，需要湿实验确认。",
            source_type="文献",
            construct_length=len(PPA_EPX1_SA_SP) + len(MATURE_OPN),
        ),
    ]


def opn_library_service() -> SignalPeptideLibraryService:
    return SignalPeptideLibraryService(opn_candidates(), candidate_prefix="OPN_UNIPROT")

