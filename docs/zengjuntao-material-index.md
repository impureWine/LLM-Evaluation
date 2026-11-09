# 曾俊涛负责的材料索引

截至 2026-11-09，本索引记录仓库现有材料，不把冒烟测试当成正式评测。整理时所依据的远程 `main` 基线为 `bba9158e3e9fbc3b103dd9de131cb1f87b4e78c3`。后续材料状态以仓库最新提交及真实运行记录为准。

| 材料 | 位置 | 当前状态 |
| --- | --- | --- |
| 远程仓库 | <https://github.com/impureWine/LLM-Evaluation> | 项目地址；以最新提交为准 |
| 四轮批量运行入口 | `src/llm_eval/evaluate.py` | 已有；正式配置仍需冻结 |
| 候选评测协议 | `docs/evaluation-protocol-v1.md` | 已有；待团队确认冻结 |
| 车型与三场景 | `configs/evaluation-v1.json`、`configs/scenario-rules-v1.json` | 教学模拟版及逐轮脚本已由庄剀涵交付；待团队冻结 |
| 来源与逐轮参考集合 | `data/vehicle-sources-v1.json`、`data/reference-answers-v1.json` | 已交付，可用于人工评分复核；不得发送参考答案给模型 |
| 数据预检与版本指纹 | `src/llm_eval/dataset.py`、`data/release-v1.json` | 离线校验已有证据；状态仍为待团队冻结 |
| 模型配置 | `configs/models.json` | 两个模型标识已有；对照模型默认禁用 |
| 提示词和输出契约 | `prompts/` | 已有版本化文件 |
| 接入冒烟证据 | `evidence/` | 已有；不计入 18 次正式运行 |
| 运行清单与执行指标生成器 | `src/llm_eval/run_report.py` | 已完成本地文件；待真实日志验证 |
| 18 次运行计划 | `docs/zengjuntao-run-plan.csv` | 已完成本地计划表；不代表已执行 |
| 执行与复现说明 | `docs/zengjuntao-execution-and-reproduction.md` | 已完成本地草稿；实际复现栏待填写 |
| 量化对比博客段落 | `docs/zengjuntao-blog-section.md` | 指标口径已写；实测数值待填写 |
| 正式原始日志 | `runs/` | 尚未产生；该目录被 Git 忽略 |
| 运行清单与执行汇总 | `local/run-report/` | 待正式运行后生成；该目录被 Git 忽略 |
| 评分结果与购车任务成功率 | 待关欣评分及正式日志 | 未完成 |
| 参数表、可视化与博客量化结论 | 待程杰解析、图表及正式日志 | 未完成 |
| 费用统计 | 待实际计费或额度证据 | 未完成，不估算虚构费用 |

正式公开材料需从本地日志中选取脱敏副本，并在博客中给出可访问链接。完成后在此表中填入具体文件和运行 ID。
