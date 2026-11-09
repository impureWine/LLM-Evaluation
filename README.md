# LLM 购车决策评测

本仓库用于自动化评测两个大语言模型在统一多轮购车决策任务中的表现。

当前模型接入由程群维护。主模型已切换为智谱 `glm-4.7-flash`：

| 配置键 | 精确模型标识 | 平台 | 状态 |
| --- | --- | --- | --- |
| `zhipu_glm_47_flash` | `glm-4.7-flash` | 智谱 BigModel | 启用 |
| `zhipu_glm_47` | `glm-4.7` | 智谱 BigModel | 默认禁用 |

两个候选模型共享温度、`top_p`、最大输出长度和 JSON 输出模式。`glm-4.7` 需要先确认额度并由
团队批准后再启用。模型标识、记录日期和试调用依据见 `configs/models.json`。

## 本地运行

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

在 `.env` 中填写 `LLM_EVAL_ZHIPU_API_KEY=新密钥`。`.env` 已被 Git 忽略，
不要把它提交到仓库。程序会优先使用当前终端进程已有的同名环境变量；若没有，再读取本地
`.env`。为了兼容已经填写的旧项目变量，加载器只会在新变量为空时读取
`LLM_EVAL_DEEPSEEK_API_KEY`，不会读取个人账户中的 `DEEPSEEK_API_KEY`。
如果你已经在 `.env` 中填写了旧变量，不需要重新输入密钥；新版加载器会自动完成兼容映射。

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## 智谱主模型连通性冒烟测试

先做不消耗额度的本地检查：

```powershell
$env:PYTHONPATH = "src"
python -m llm_eval.smoke --dry-run
```

再调用两个模型各一次：

```powershell
python -m llm_eval.smoke --model zhipu_glm_47_flash `
  --out evidence/zhipu-glm-4.7-flash-smoke-success-2026-11-07.json
```

该脚本使用 `examples/smoke_case.json` 的教学模拟车型库，只验证模型标识、鉴权、多轮上下文入口、
JSON 模式、Schema 校验和纠正重试链路，不计入正式实验。

智谱聊天接口已验证 `glm-4.7-flash`：服务端返回 HTTP 200 并回显该模型 ID。由于该账号的
`/models` 列表没有枚举此模型，`configs/models.json` 将直接聊天验证结果作为接入依据。

## 程群交付材料

- [模型接入与统一配置说明](docs/model-access-and-configuration.md)
- [技术改进与备选方案比较](docs/technical-improvement.md)
- [博客初稿](docs/chengqun-blog-draft.md)
- [双模型实际接入证据](evidence/README.md)

## 目录

- `configs/`：版本化模型配置与共享参数。
- `src/llm_eval/`：模型适配、错误处理和后续提示词工具。
- `prompts/`：两个模型共用的提示词与输出契约。
- `docs/`：接入记录、方案比较和博客材料。
- `tests/`：不消耗 API 额度的自动测试。

## 统一提示词

`PromptBundle.from_directory()` 会读取版本化提示词和
`prompts/output_schema_v1.json`，生成 SHA-256 指纹。正式实验应把该指纹写入每次运行记录，
以证明两个模型使用同一测试条件。

`SchemaValidatedDecisionClient` 在模型返回后执行 JSON 解析和关键字段校验；失败时最多追加一次
统一的纠正消息。首次输出和纠正输出都会保留在结果审计记录中。


## 张王昊交付材料

- [分工进度、验收清单与提交记录](docs/evaluation-coordination.md)
- [博客整合稿、开发时间估计与模型选型建议](docs/evaluation-blog.md)
- [程杰结果提取与图表说明](docs/results-report.md)

## 郭昱祺交付材料

- [个人交付与剩余证据](docs/guo-yuqi-delivery.md)
- [两个模型的产品体验与改进分析](docs/guo-yuqi-product-experience.md)
- [采访执行包（含统一四轮任务）](docs/guo-yuqi-interview-kit.md)、[空白记录表](evidence/guo-yuqi-interview-template.md)
- [产品规划、NABCD与功能优先级](docs/guo-yuqi-product-plan.md)
- [官方页面截图与证据索引](evidence/guo-yuqi/README.md)

当前已形成报告、规划及采访材料；真实学生采访、登录后的完整产品操作与第二模型对话仍待补证，详见交付索引。

## 四轮评测联调

使用 `python -m llm_eval.evaluate --dry-run` 查看模型、场景、指纹和计划任务数。实际联调、实验冻结与评分参见[评测协议 v1](docs/evaluation-protocol-v1.md)。

## 结果提取

正式批次运行后，使用 `python -m llm_eval.report` 从 `runs/` 导出初选候选、第三轮参数对比、最终推荐、逐次运行摘要及模型汇总表，并生成完成率图。该命令不调用模型；冒烟和联调批次不会混入正式结果。输出字段及口径见[结果提取说明](docs/results-report.md)。

## 庄剀涵交付材料

- [任务交付与复现索引](docs/zhuang-kaihan-delivery.md)
- [车型数据、来源口径、三场景与需求变更脚本](docs/zhuang-kaihan-data-and-scenarios.md)
- [市场概况、用户分析与商业模式](docs/zhuang-kaihan-market-and-business.md)
- [车型来源与字段字典](data/vehicle-sources-v1.json)、[逐轮约束与脚本](configs/scenario-rules-v1.json)
- [逐轮参考集合与排除原因](data/reference-answers-v1.json)、[输入版本指纹](data/release-v1.json)
- [市场来源表](data/market-sources-v1.json)、[来源核验摘录](evidence/market-source-excerpts-2026-11-09.md)

沿用原 `configs/evaluation-v1.json` 的五款教学模拟车型及三个场景，参数与运行消息保持兼容。
在正式运行前增加零 API 调用的数据校验：

```powershell
$env:PYTHONPATH = 'src'
python -m llm_eval.dataset
```

该命令核对来源、参考集合、约束变更、脚本与运行器一致性、答案隔离及输入指纹。
材料状态是“供团队冻结审核”，不是正式模型运行或团队审批的完成记录。

## 关欣交付材料

- [评分细则、判定口径与冻结记录](docs/evaluation-protocol-v1.md)
- [规则评分实现](src/llm_eval/scoring.py)、[离线评分测试](tests/test_scoring.py)
- [边界案例 C1：结构通过但追问含两个问题](docs/case-c1-question-count.md)
- [边界案例 C2：需求变更后的预算边界与无解表达](docs/case-c2-budget-boundary.md)、[边界回归测试](tests/test_boundary_change.py)
- [现实影响与工程改进（博客第二部分正文）](docs/reality-impact-and-bug-analysis.md)
- [回填清单：正式批次到位后要改什么](docs/backfill-checklist.md)
- [公开材料脱敏检查记录](docs/desensitization-check.md)

评分在正式运行后离线执行，不消耗 API 额度：

```powershell
$env:PYTHONPATH = 'src'
python -m llm_eval.scoring --runs runs/<批次>
# 人工复核 review-queue.csv 并回填 verdict 后重算
python -m llm_eval.scoring --runs runs/<批次> --review runs/<批次>/scores/review-queue.csv
```

`scores.csv` 为逐次分数、失败项与最终推荐车型，`summary.csv`、`summary.md` 为模型×场景汇总
（含推荐分布），`review-queue.csv` 为人工判定项：`blocking` 缺证据待判、`override` 可改判，
`review-hints.csv` 只作复核提示、不影响分数。
评分细则、评分实现与参照数据须同批冻结，改动按协议第 10 节升版本并重算指纹。
