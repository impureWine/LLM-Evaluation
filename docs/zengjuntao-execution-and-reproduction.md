# 实验执行、统计与复现（曾俊涛）

远程仓库：<https://github.com/impureWine/LLM-Evaluation>。本文件是执行说明，不代表正式实验已经完成。

## 运行前核对

1. 由团队确认并冻结 `configs/evaluation-v1.json`、`configs/scenario-rules-v1.json`、`data/reference-answers-v1.json`、`configs/models.json`、`prompts/` 和 `docs/evaluation-protocol-v1.md`，记下 Git 提交及文件指纹。`data/release-v1.json` 当前状态为 `prepared_for_team_freeze`，不等于团队已冻结；第二模型仍默认禁用。
2. 核实两个模型的可调用性、额度和可能费用；将项目密钥放在本机 `.env` 或环境变量中。不得把密钥放进仓库、博客或公开日志。
3. 在仓库根目录安装项目并执行不调用 API 的预检：

   ```powershell
   python -m pip install -e .
   $env:PYTHONPATH = 'src'
   python -m unittest discover -s tests -v
   python -m llm_eval.dataset
   python -m llm_eval.evaluate --dry-run
   ```

4. 联调每个模型与场景的四轮流程。联调标为 `pilot`，不能算入 18 次正式运行。确认候选提取、参数对比、最终推荐、日志、错误和重试可回查。若团队改变数据、提示词或评分规则，重新记录冻结版本。

## 正式执行与数据保护

冻结后由负责人启动三次重复运行，计划为 2 模型 × 3 场景 × 3 次 = 18 个四轮任务。执行前逐项核对[18 次计划清单](zengjuntao-run-plan.csv)；该清单仅为计划，不能作为已运行证据。批量入口当前把三次重复日志标为 `evaluation_candidate`；只有确认冻结及实际执行条件后，才能将该批次认定为正式实验。`runs/` 被 Git 忽略；保留原始记录及失败、补跑的独立批次，不覆盖原文件。共享材料前人工检查响应中可能含有的个人信息、密钥或其他敏感内容。

在仓库根目录生成运行清单与执行指标：

```powershell
$env:PYTHONPATH = 'src'
python -m llm_eval.run_report --runs-dir runs --out-dir local/run-report
```

如果存在多次同配置批次，用 `--batch 批次目录名` 单独统计，避免把补跑与原运行混在同一分母中。

输出 `run_inventory.csv` 和 `execution_summary.json`。脚本只统计**四轮结构完成率**、任务墙钟耗时及可读到的 token 用量；它不计算课程要求的购车任务成功率或质量分。报告按模型、场景分组，列出样本数与极差。运行记录的车型数据、提示词或评分指纹不一致时拒绝混合汇总。没有运行日志时，输出零条记录，不生成虚构结果。

## 评分复核与博客交接

按冻结评分规则逐条回查四轮原始响应，确认最终车型满足当前约束、车型事实与固定数据一致。与关欣核对评分，与程杰核对候选、参数表、最终推荐和图表；将运行 ID、原始文件、差异和处理结论记入复核表。购车任务成功率依协议的四轮结构、最终约束和真实性判定计算，分母为计划内已发起任务；失败与中断保留在分母，未发起单列。不得将 `structure_completion_rate` 当作购车任务成功率。

交张王昊整合的材料：仓库链接、冻结配置和提示词、脱敏原始日志、运行清单、评分结果、图表、指标定义及样本数、复现检查结果。每场景仅三次重复，结论只适用于本次数据与设置。公开前抽查博客目录和附件链接，并预留审核时间。

## 待实际填写的复现记录

| 日期/执行人 | 冻结提交与指纹 | Python 版本 | 实际命令 | 结果与日志位置 | 问题及处理 |
| --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |
