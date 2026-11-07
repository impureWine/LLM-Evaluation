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
$env:DEEPSEEK_API_KEY = "你的密钥"
```

密钥只从环境变量读取，不要把真实密钥写入配置文件或提交到仓库。

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

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

