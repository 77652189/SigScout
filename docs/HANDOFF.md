# SigScout Handoff

```yaml
slice_status: complete
current_slice: fusion_target_isolation
next_action: recompute_localization_results
```

## 当前目标

完成融合构建、定位结果和 Streamlit 业务状态的目标隔离，保留共享宿主信号肽候选库。旧定位结果不兼容 schema v2。

## 下一步

按目标重新生成 FASTA，在外部定位工具中重算并分别导入结果。后续产品开发仍需从[执行计划](EXECUTION_PLAN.md)选择或新增授权切片。

## 必读材料

1. [需求](REQUIREMENTS.md)的能力与信息披露边界。
2. [架构](ARCHITECTURE.md)的依赖方向与不变量。
3. [执行计划](EXECUTION_PLAN.md)的待授权方向和重新评估门槛。
4. [ADR 索引](adr/README.md)中的长期决策。

## 验证方式

本切片运行完整 pytest、`python -m compileall -q src tests sigscout` 与 `git diff --check`，并重启 Streamlit 检查目标切换、构建恢复和上传入口。页面级冒烟测试不能替代交互走查。

## 硬约束

公开 README 与受跟踪工程文档不得出现具体目标蛋白名称、其 accession 或点名该目标的文献引用。

实验引导结果不得表述为真实分泌产量预测、跨批次比较或统计显著性结论。

短信号肽与完整 leader 不得在同一实验引导评分中直接混合比较。

实验反馈只按精确氨基酸序列关联；仅 A 段一致不得表述为完整构建已经验证。

目标专属实验反馈、融合构建和定位缓存不得跨目标复用。

融合构建身份必须同时包含目标边界、schema 版本与完整序列摘要；旧版定位结果不得自动迁移。

未经明确授权，不提交、不推送、不改变远端可见性。
