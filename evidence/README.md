# 模型接入证据

## 结果汇总候选修订

[v1.1候选数据校验](data-validation-2026-11-09-v1.1-candidate.json)记录结构化参数对比输出契约的离线校验。此版本仍待团队冻结；该文件不是正式运行结果，也不包含模型评分。

## 郭昱祺的体验及采访材料

[页面证据索引](guo-yuqi/README.md)保存2026-11-09官方功能页、登录入口截图及原始页面文本；[空白采访表](guo-yuqi-interview-template.md)配合[采访执行包](../docs/guo-yuqi-interview-kit.md)使用。目前没有真实采访或GLM-4.7成功对话，页面图片不计入模型运行或采访完成数。

## 当前：智谱 GLM-4.7-Flash

- `zhipu-glm-4.7-flash-smoke-2026-11-07.json`：关闭思考模式前的完整请求超时记录。
- `zhipu-glm-4.7-flash-smoke-success-2026-11-07.json`：设置 `thinking.type=disabled` 后的成功
  记录。请求模型与服务端回显均为 `glm-4.7-flash`，`finish_reason=stop`，Schema 通过。
- 运行方式：`python -m llm_eval.smoke --model zhipu_glm_47_flash`。
- 智谱 `glm-4.7-flash` 为免费模型；实际额度和限流以智谱账户页面为准。

## 历史：DeepSeek 接入测试

`model-smoke-2026-11-07.json` 记录了程群负责的模型接入冒烟测试。

- 时间：2026-11-07，北京时间约 11:32 至 11:33。
- 场景：`examples/smoke_case.json`，教学模拟数据。
- 调用方式：`python -m llm_eval.smoke --out evidence/model-smoke-2026-11-07.json`。
- 性质：不计入正式实验，不用于稳定性或模型排名结论。
- 统一条件：同一车型库、同一提示词、同一参数和同一 JSON Schema。

该文件保存请求模型、服务端回显模型、`finish_reason`、token 用量、延迟、重试次数、
提示词指纹以及模型最终回复。API Key 未写入文件。

该历史证据生成时项目读取的是 `DEEPSEEK_API_KEY`。之后已将当前配置隔离为
`LLM_EVAL_DEEPSEEK_API_KEY`，历史证据保持原样以保持审计真实性。

当前主模型已切换为智谱 `glm-4.7-flash`，因此本目录中的 DeepSeek 文件只是先前接入测试的
历史证据，不代表当前正式测评对象。

