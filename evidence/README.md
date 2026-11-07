# 模型接入证据

`model-smoke-2026-11-07.json` 记录了程群负责的模型接入冒烟测试。

- 时间：2026-11-07，北京时间约 11:32 至 11:33。
- 场景：`examples/smoke_case.json`，教学模拟数据。
- 调用方式：`python -m llm_eval.smoke --out evidence/model-smoke-2026-11-07.json`。
- 性质：不计入正式实验，不用于稳定性或模型排名结论。
- 统一条件：同一车型库、同一提示词、同一参数和同一 JSON Schema。

该文件保存请求模型、服务端回显模型、`finish_reason`、token 用量、延迟、重试次数、
提示词指纹以及模型最终回复。API Key 未写入文件。

