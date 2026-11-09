# 回填清单：正式批次到位后要改什么

> 用途：`runs/` 里出现正式批次后，照这份清单逐条勾选，约 40 分钟完成回填。
> 不适用：pilot、边界补测、冒烟记录——这些只在案例里单列，不触发第 2 节的正式数字回填。

## 0. 触发条件

- `runs/<批次>/` 出现 `batch_kind: evaluation_candidate` 的记录，满 18 条或部分完成。
- 只有部分批次时，只填已完成的数字，未执行的写“未执行”，不得用 0 或空值冒充分母。
- 若 `glm-4.7` 最终未启用，则只有单模型数据：第 2 节所有“两模型对比”类表述改为“单模型结果 + 未执行说明”。

## 1. 五步操作

| 步 | 命令 | 产物 | 检查点 |
| ---: | --- | --- | --- |
| 1 | `python -m llm_eval.run_report --runs-dir runs` | `local/run-report/run_inventory.csv`、`execution_summary.json`（不入库） | 18 条是否齐全；`usage_complete` 是否有 false |
| 2 | `python -m llm_eval.scoring --runs runs/<批次>` | `runs/<批次>/scores/` 下 `scores.csv`、`summary.csv`、`summary.md`、`review-queue.csv` | `pending_points` 是否为 0；不为 0 则进第 3 步 |
| 3 | 打开 `review-queue.csv`，在 `verdict` 列填 `pass` 或 `fail`，再执行 `python -m llm_eval.scoring --runs runs/<批次> --review runs/<批次>/scores/review-queue.csv` | 重算后的同一批文件 | `blocking` 行必须全部有结论；`override` 行不改也可以 |
| 4 | 把 `summary.csv` 交给程杰出图 | 图表 | 图表数字与 `scores.csv` 逐格一致 |
| 5 | 按第 2 节回填文档 | 博客、案例、协调文档 | 三处数字一致（博客表 / `summary.md` / 图表） |

评分表要公开的话，把 `scores.csv`、`summary.md` 复制到 `evidence/` 或 `docs/`；**原始 run 记录不直接公开**（含完整模型响应与响应 ID），需要时先脱敏。

## 2. 待回填位置（逐条勾选）

| # | 文件与位置 | 现在写的 | 改成 | 数据来源 | 负责人 |
| ---: | --- | --- | --- | --- | --- |
| 1 | [`evaluation-blog.md`](evaluation-blog.md) 第 58 行 | “正式结果待附评分表、按场景的成功数与样本数、耗时与 token 汇总及至少两个可回溯案例” | 贴评分表 + 成功数/样本数 + 耗时与 token + 案例链接 | `summary.csv`、C1/C2 | 张王昊、关欣 |
| 2 | [`evaluation-blog.md`](evaluation-blog.md) 第 107 行 | “待汇入现实影响、正式案例及 BUG 原因分析” | 换成[正文](reality-impact-and-bug-analysis.md)或至少加链接 | 已定稿 | 张王昊（待确认） |
| 3 | [`reality-impact-and-bug-analysis.md`](reality-impact-and-bug-analysis.md) 第 4 行 | “截至 2026-11-09，仓库内尚无正式 18 次批次记录” | 改为实际完成日期与批次号 | `run_inventory.csv` | 关欣 |
| 4 | 同上 第 74 行 P7 | “正式 18 次批次尚未汇入” | 改为“已于 X 完成 N 次”或保留未完成说明 | 同上 | 关欣 |
| 5 | 同上 第 131 行“局限与待回填” | “没有一个判断依赖正式 18 次结果” | 若引用正式结果，逐句标注来源批次数 | `summary.csv` | 关欣 |
| 6 | 同上 §1.5 延迟段 | 只有冒烟样本 89.282 s | 可补正式批次的平均任务耗时与单轮响应时间，并注明样本数 | `summary.csv` | 关欣 |
| 7 | [`evaluation-coordination.md`](evaluation-coordination.md) 第 13 行 | “正式规则与分析待汇入” | 改为“评分规则与案例已入库，评分表见 …” | 提交记录 | 张王昊 |
| 8 | [`desensitization-check.md`](desensitization-check.md) §6 基线 | `main` @ `bba9158` | 发布前复检时更新为当时的 `main` 哈希 | `git rev-parse main` | 关欣 |
| 9 | `README.md` 关欣段 | 只有规则、案例、分析、脱敏 | 若评分表入库，补一行链接 | `docs/` 或 `evidence/` | 关欣 |
| 10 | 案例目录 | 只有 C1、C2 | **不改写 C1/C2**；正式批次出现新失败时新增 C3 | `scores.csv` 的 `failed_checks` | 关欣 |

## 3. 要填的数字与口径

| 指标 | 取自 | 单位 | 注意 |
| --- | --- | --- | --- |
| 已发起任务数 | `runs` | 次 | 分母，含失败与超时 |
| 成功数 / 成功率 | `success` ÷ `runs` | 次 / % | 未定（`undecided`）在复核前不计入成功 |
| 均分、最小、最大、标准差 | `mean_score`、`min_score`、`max_score`、`stdev_score` | 分 | 三次运行才有标准差；样本少要写明 |
| 待复核分值 | `pending_points` | 分 | 必须为 0 才能发布正式结论 |
| 平均 token | `mean_tokens` | tokens | 空白表示缺失，**不得填 0** |
| 平均任务耗时 | `mean_elapsed_s` | 秒 | 与 `run_inventory.csv` 的 `mean_task_seconds` 应对得上 |
| 推荐分布 | `recommendation_mix` | — | 描述性统计，不参与评分 |

fail 项的原因代码在 `scores.csv` 的 `failed_checks` 列，格式为 `维度#轮次:原因`，可直接引用进案例。

## 4. 交叉核对（数字对不上先查批次）

| 对谁 | 核对什么 | 常见不一致原因 |
| --- | --- | --- |
| 程杰 | 图表数值 = `scores.csv` 逐格一致 | 图表用了旧的 `summary.csv`，或混入了 pilot |
| 曾俊涛 | 任务数与耗时 = `run_inventory.csv` | 批次不同；或一边含失败任务一边剔除 |
| 张王昊 | 成功率定义 = 协议第 8 节 | 把“四轮结构完成”当成“任务成功” |
| 自己 | `summary.md` 与 `summary.csv` 同源 | 手改过 md 忘了改 csv |

## 5. 冻结后的红线

- 不改协议、提示词、车型数据；确需修改 → 升版本、重算指纹、新批次，不混算。
- 不覆盖原 run 文件；补跑另起批次，原批次保留。
- 补测与 pilot 不进 18 次分母，也不进正式成功率。
- 不手工改 `scores.csv` 的分数；改判只走 `review-queue.csv` 的 `verdict`。
- 评分规则文本、`scoring.py`、`reference-answers-v1.json` 三处必须一致。

## 6. 发布前 15 分钟复检

1. `python -m llm_eval.dataset` 返回 `valid: true`（指纹未被改动）。
2. `python -m unittest discover -s tests` 全绿（当前 58 项）。
3. 重跑[脱敏检查](desensitization-check.md)第 2 节的命令，确认无新增命中。
4. **CSDN 链接替换**：博客里的相对链接（`docs/xxx.md`、`../evidence/xxx.json`）在 CSDN 点不开，须改成
   `https://github.com/impureWine/LLM-Evaluation/blob/main/<路径>`。
   涉及文件：[C1](case-c1-question-count.md)、[C2](case-c2-budget-boundary.md)、[正文](reality-impact-and-bug-analysis.md)、[脱敏记录](desensitization-check.md)。
5. 三处数字一致：博客表格、`summary.md`、程杰的图表。
6. 免责声明在位：结论只适用于本次教学模拟数据、三场景与三次重复，不代表行业排名。

## 7. 当前仍待确认（会阻塞本清单）

| 事项 | 找谁 | 影响 |
| --- | --- | --- |
| `glm-4.7` 是否启用 | 张王昊、程群 | 不启用则第 2 节全部“两模型对比”表述要改写 |
| PR#1 是否合并 | 李泉毅 | 不合并则第 3 轮真实性一直是有 `blocking` 待判 |
| 博客第 107 行是否换成正文 | 张王昊 | 决定现实影响一节以什么形式进博客 |
| 18 次何时起跑 | 曾俊涛 | 触发本清单的前提 |
