# 模型接入与统一配置说明

## 1. 本部分范围

程群在本项目中负责以下交付物：

1. 试调用并接入两个不同的大模型。
2. 记录平台、精确模型标识、日期和生成参数。
3. 设计两个模型共用的多轮提示词与输出要求。
4. 处理模型接入、上下文状态边界和可重试错误。
5. 提出一项技术改进方案，与备选方案比较并给出验证方法。
6. 提供稳定接口供自动化测试、解析和汇总模块复用。

对应代码位于 `src/llm_eval/`，提示词位于 `prompts/`，模型配置位于
`configs/models.json`，接入证据位于 `evidence/model-smoke-2026-11-07.json`。

## 2. 被测模型

| 配置键 | 精确模型标识 | 角色定位 | 服务端回显 |
| --- | --- | --- | --- |
| `deepseek_flash` | `deepseek-flash` | 通用快速模型（官方当前由 V4.1-1017 提供） | `deepseek-flash` |
| `deepseek_v4_pro` | `deepseek-v4-pro` | 高阶能力模型 | `deepseek-v4-pro` |

平台为 DeepSeek API。2026-11-07 通过 `GET https://api.deepseek.com/models`
确认两个模型标识均被平台发布，并通过两次真实的 `/chat/completions` 请求确认服务端分别回显了
上述精确标识。这里使用的是两个不同模型，不是同一模型的温度、提示词或参数变体。

没有使用本地 Codex 配置中的 `deepseek-v4-flash` 别名作为正式模型标识。正式记录以服务端接受并
回显的 `deepseek-flash` 和 `deepseek-v4-pro` 为准。

DeepSeek 官方文档在 2026-11-07 说明 `deepseek-flash` 当前由
`DeepSeek-V4.1-Flash-1017` 提供服务，并明确列出精确模型标识为 `deepseek-flash`。
官方页面没有发布名为“4.7 Flash”的 API 标识，因此项目不能自行猜测为
`deepseek-v4.7-flash`。更换平台或模型时，必须用新密钥请求该平台的 `/models`，记录完整返回值。

## 3. 统一生成参数

两个模型共享以下配置：

| 参数 | 值 | 目的 |
| --- | --- | --- |
| `temperature` | `0.0` | 尽量降低采样随机性，便于重复运行 |
| `top_p` | `1.0` | 不额外截断候选词分布 |
| `max_tokens` | `4096` | 给推理内容和完整 JSON 留足空间 |
| `stream` | `false` | 简化原始记录和超时处理 |
| `response_format` | `{"type": "json_object"}` | 启用平台 JSON 输出模式 |

说明：`max_tokens` 是输出上限而不是实际计费量。试调用发现推理类输出会先占用内部推理 token，
若上限过小会出现 `finish_reason=length` 且最终 JSON 为空，因此统一提高到 4096。

## 4. 实际接入证据

2026-11-07 使用同一提示词指纹
`4ffc5f7ddcac9c3aa1e03a1f33ddb9931418d93c418c573113f0c8bcf4acd811`
对两个模型各执行一次非正式冒烟任务：

| 模型 | 输出校验 | `finish_reason` | 总 token | 端到端延迟 | 纠正次数 |
| --- | --- | --- | ---: | ---: | ---: |
| `deepseek-flash` | 通过 | `stop` | 3521 | 12.500 s | 0 |
| `deepseek-v4-pro` | 通过 | `stop` | 4468 | 31.938 s | 0 |

本次任务只有一个样本，延迟和 token 只证明链路可用，不能据此判断稳定均值、性价比或最终排名。
正式结论必须使用团队规定的 18 次完整多轮运行及统一评分规则。

在冒烟场景中，两个模型都能从给定车型库排除超预算的第三辆车，并引用真实存在的 `source_id`。
它们对最终推荐存在差异：`deepseek-flash` 推荐纯电紧凑型轿车 A，
`deepseek-v4-pro` 推荐插电混动紧凑型 SUV B，并额外考虑充电条件不明确时的补能灵活性。
该差异可作为后续正式评测中“推荐理由是否覆盖用户风险”的观察点，但两者均不代表真实市场车型。

## 5. API 接入设计

`OpenAICompatibleClient.complete(spec, messages)` 提供统一调用入口：

1. 从 `spec.api_key_env` 指定的环境变量读取密钥。
2. 将完整消息列表原样发送给 `/chat/completions`。
3. 记录服务端实际返回的模型 ID、响应 ID、token 用量、耗时和 `finish_reason`。
4. 只保留最终 `content`；若接口返回 `reasoning_content`，仅记录是否存在，不把内部推理继续送入对话。
5. 对超时、`408`、`409`、`429` 和 `5xx` 做指数退避重试。
6. 对普通 `4xx` 不重试，避免错误请求重复消耗额度。
7. 不记录 Authorization 请求头。

调用方不需要知道具体平台，只需要从注册表取得 `ModelSpec`。以后新增兼容接口的模型时，
主要工作是增加配置，而不是修改评测主流程。

## 6. 上下文与运行隔离

模型客户端本身是无状态的，每次 `complete` 调用只接收调用方传入的完整消息列表。因此：

- 同一次多轮任务中，自动化框架必须把此前的 `system`、`user` 和 `assistant` 消息继续传入。
- 不同独立运行必须创建新的消息列表，不得复用上一轮运行对象。
- 需求修改发生在后续轮次时，用户消息应通过 `PromptBundle.followup_message()` 加入轮次编号和
  变更生效规则。
- 数据库、缓存和密钥配置不得成为跨运行隐式上下文。

这种边界把“模型无状态”和“任务有状态”分开：模型接入层不自行保存会话，李泉毅负责的自动化
框架明确控制每次运行的上下文生命周期，便于复盘和复现。

## 7. 统一提示词与输出契约

两个模型完全共用：

- `prompts/system_v1.md`
- `prompts/initial_user_v1.md`
- `prompts/followup_user_v1.md`
- `prompts/output_schema_v1.json`

系统提示词要求模型只使用给定车型库、保留仍有效的约束、标记被后续需求替换的旧约束、
引用来源编号并区分最终推荐与追问。输出契约包含有效约束、候选车型、最终推荐、下一问题、
置信度、状态和假设。

`PromptBundle` 会计算四个文件的 SHA-256 指纹。每次运行记录该指纹，可以证明两个模型在提示词
层面使用了同一条件。若提示词发生修改，必须升级版本并重新计算指纹。

## 8. 供其他模块使用的接口

最小接入示例：

```python
from llm_eval.config import load_model_registry
from llm_eval.openai_compatible import OpenAICompatibleClient
from llm_eval.prompts import PromptBundle
from llm_eval.structured import SchemaValidatedDecisionClient

registry = load_model_registry()
bundle = PromptBundle.from_directory()
messages = bundle.initial_messages(scenario, vehicle_data)

client = SchemaValidatedDecisionClient(
    base_client=OpenAICompatibleClient(),
    prompt_bundle=bundle,
    max_corrections=1,
)

for spec in registry.ordered():
    result = client.complete(spec, messages)
    record = result.as_record()
```

建议统一运行日志至少保存以下字段：

| 字段 | 含义 |
| --- | --- |
| `run_id` | 独立运行编号 |
| `scenario_id` | 场景编号 |
| `turn_number` | 当前轮次 |
| `model_key` | 团队配置键 |
| `requested_model` | 请求中的精确模型 ID |
| `served_model` | 服务端回显模型 ID |
| `prompt_fingerprint` | 提示词版本指纹 |
| `parameters` | 实际生成参数 |
| `total_usage` | 包含纠正调用的 token 总量 |
| `total_latency_ms` | 包含重试与纠正的累计耗时 |
| `valid` | 是否通过 JSON 与 Schema 校验 |
| `correction_attempts` | 纠正调用次数 |
| `parsed_output` | 通过校验后的结构化结果 |
| `attempts` | 每次请求的原始文本与指标 |

## 9. 密钥与公开材料

- 真实密钥从项目专用环境变量 `LLM_EVAL_DEEPSEEK_API_KEY` 读取。
- 程序支持读取本地 `.env`，但不会覆盖当前终端进程已有的同名环境变量。
- `.env` 已加入 `.gitignore`；仓库配置和公开证据不包含该变量的值。
- 配置文件加载时若检测到形似 `sk-...` 的凭据会直接报错。
- 提交前已检查 `evidence/`、`configs/`、`prompts/` 和 `src/`，未发现凭据值。

## 10. 当前限制

1. 本次冒烟测试只有每个模型一个样本，不能计算成功率、波动或稳定排名。
2. 正式场景、车型数据和需求变更脚本还未纳入本分支，冒烟车型库不得替代庄剀涵维护的数据集。
3. DeepSeek 平台支持当前 JSON 模式，但若团队后续引入不支持该参数的其他平台，需在配置和
   公平性说明中单独记录，不能静默改变条件。
4. 工具调用仍是选做项。本接入层没有把工具调用伪装成已完成成果。

