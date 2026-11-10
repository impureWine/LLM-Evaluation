# 曾俊涛离线预检记录（2026-11-10）

执行位置：仓库根目录。环境：Windows PowerShell、Python 3.14.6。以下命令没有调用模型 API。

| 命令 | 实际结果 |
| --- | --- |
| `python -m unittest discover -s tests -v`（`PYTHONPATH=src`） | 73 项通过，`OK`；包含 `test_run_report.py` 的 4 项测试 |
| `python -m llm_eval.dataset` | `valid: true`、5 款教学模拟车、3 个场景、12 轮参考核验、`api_calls: 0` |
| `python -m llm_eval.evaluate --dry-run` | 2 个模型、3 个场景、计划 18 个四轮任务、`api_calls: 0` |
| `python -m llm_eval.run_report --runs-dir runs --out-dir local/run-report` | 0 条运行记录；输出空清单和空汇总，不含实验结论 |

预检时输入版本为 `v1.1-candidate`；`data/release-v1.json` 状态为 `prepared_for_team_freeze`，团队冻结尚未登记。`glm-4.7` 仍默认禁用；仓库根目录没有 `.env` 或正式 `runs/` 批次。本记录不证明双模型联调、18 次实验、人工评分或付费额度已经完成。

`unittest` 中评分 CLI 测试会在 Git 忽略的测试目录创建模拟运行文件；这些是离线夹具，不是正式模型响应。
