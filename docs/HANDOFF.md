# SigScout Handoff

```yaml
slice_status: awaiting_authorization
current_slice: none
next_action: choose_authorized_direction
```

## 当前目标

等待下一项获得授权、具备验收标准的产品开发或验证切片。

## 下一步

从[执行计划](EXECUTION_PLAN.md)的待授权方向中选择下一项，或提供新的目标与验收标准。

## 必读材料

1. [需求](REQUIREMENTS.md)的能力与信息披露边界。
2. [架构](ARCHITECTURE.md)的依赖方向与不变量。
3. [执行计划](EXECUTION_PLAN.md)的待授权方向和重新评估门槛。
4. [ADR 索引](adr/README.md)中的长期决策。

## 验证方式

按变更范围运行相关 pytest；修改 Python 结构后运行 `python -m compileall src tests sigscout`；修改 CLI 或 UI 时分别检查 CLI 帮助和受影响的 Streamlit 页面。页面级冒烟测试不能替代交互走查。

## 硬约束

公开 README 与受跟踪工程文档不得出现具体目标蛋白名称、其 accession 或点名该目标的文献引用。

实验引导结果不得表述为真实分泌产量预测、跨批次比较或统计显著性结论。

短信号肽与完整 leader 不得在同一实验引导评分中直接混合比较。

实验反馈只按精确氨基酸序列关联；仅 A 段一致不得表述为完整构建已经验证。

目标专属实验反馈、融合构建和定位缓存不得跨目标复用。

未经明确授权，不提交、不推送、不改变远端可见性。
