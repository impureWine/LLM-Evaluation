# LLM 购车决策评测

本仓库用于自动化评测两个大语言模型在统一多轮购车决策任务中的表现。

当前模型接入由程群维护，已登记两个真实可调用的不同模型：

| 配置键 | 精确模型标识 | 定位 |
| --- | --- | --- |
| `deepseek_flash` | `deepseek-flash` | 通用快速模型 |
| `deepseek_v4_pro` | `deepseek-v4-pro` | 高阶能力模型 |

两个模型共享温度、`top_p`、最大输出长度和 JSON 输出模式；模型标识、记录日期和试调用依据见
`configs/models.json`。

## 本地运行

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
notepad .env
```

在 `.env` 中填写 `LLM_EVAL_DEEPSEEK_API_KEY=新密钥`。`.env` 已被 Git 忽略，
不要把它提交到仓库。程序会优先使用当前终端进程已有的同名环境变量；若没有，再读取本地
`.env`。使用项目专用变量名可以避免误用你个人账户里的 `DEEPSEEK_API_KEY`。

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## 双模型连通性冒烟测试

先做不消耗额度的本地检查：

```powershell
$env:PYTHONPATH = "src"
python -m llm_eval.smoke --dry-run
```

再调用两个模型各一次：

```powershell
python -m llm_eval.smoke --out evidence/model-smoke-2026-11-07.json
```

该脚本使用 `examples/smoke_case.json` 的教学模拟车型库，只验证模型标识、鉴权、多轮上下文入口、
JSON 模式、Schema 校验和纠正重试链路，不计入正式实验。

当前 DeepSeek 官方 API 的 Flash 模型标识是 `deepseek-flash`。2026-11-07 的官方文档说明它由
`DeepSeek-V4.1-Flash-1017` 提供服务，文档没有列出名为“4.7 Flash”的精确模型 ID。若新密钥来自
其他平台，或该平台明确提供 4.7 Flash，需要同时补充平台 `base_url` 和 `/models` 返回的精确 ID。

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

