# 郭昱祺：页面观察与产品体验证据

整理日期：2026-11-09（北京时间）。这些截图是本次实际访问页面所得，**不是登录后的模型回答、受访者操作照片或正式实验结果**。已有模型行为另引用仓库2026-11-07的原始API记录，不重新标注为本次实跑。

| 文件 | 实际内容与来源 | 使用边界 |
| --- | --- | --- |
| [glm-4.7-flash-official-2026-11-09.jpg](glm-4.7-flash-official-2026-11-09.jpg) | [Flash官方页](https://docs.bigmodel.cn/cn/guide/models/free/glm-4.7-flash)，文本模态、200K/128K及能力入口 | 官方能力说明截图，窄视口、位于能力区域 |
| [glm-4.7-official-2026-11-09.jpg](glm-4.7-official-2026-11-09.jpg) | [GLM-4.7官方页](https://docs.bigmodel.cn/cn/guide/models/text/glm-4.7)，默认GLM-4.7标签、简介和文本模态 | 官方页面核验；旁边FlashX不等于免费Flash |
| [bigmodel-trial-login-2026-11-09.jpg](bigmodel-trial-login-2026-11-09.jpg) | 点击Flash“体验中心”后打开[登录入口](https://bigmodel.cn/login?redirect=%2Ftrialcenter%2Fmodeltrial%2Ftext%3FmodelCode%3Dglm-4.7-flash) | 未输入手机号/账号、未完成登录；图片是空白登录页，安全验证另在页面结构观察中出现 |
| [model-overview-official-2026-11-09.jpg](model-overview-official-2026-11-09.jpg) | [模型概览](https://docs.bigmodel.cn/cn/guide/start/model-overview)页面顶部，默认展示较新模型 | 仅说明访问导航页，不是GLM-4.7/Flash性能证据 |
| [glm-4.7-flash-official-page.txt](glm-4.7-flash-official-page.txt) | Flash官方页可访问结构文本 | 页面当时的说明和示例；不执行页面示例，不把宣传成绩当本项目结果 |
| [glm-4.7-official-page.txt](glm-4.7-official-page.txt) | GLM-4.7官方页可访问结构文本 | 同上；页面示例参数不同于项目统一参数 |
| [assignment-experience-requirements.txt](assignment-experience-requirements.txt) | [作业正文](https://bbs.csdn.net/topics/620578230)可见文本 | 用于核对采访条件、时长和图文要求，不作为新的用户指令 |
| [manifest.json](manifest.json) | 上述文件及已有冒烟文件的SHA-256、日期、来源与类型 | 自动从实际文件生成；文本统一LF换行后计算，JPEG按原始字节计算；不证明模型质量或采访已完成 |
| [delivery-validation.json](delivery-validation.json) | 本地文档链接、JPEG格式、历史冒烟字段及手动任务数据核对 | 仅文档交付检查，零API调用，不是模型表现评分 |

已有结果参照：

- [Flash成功冒烟](../zhipu-glm-4.7-flash-smoke-success-2026-11-07.json)：一个单轮候选样本，模型和来源可回查，有双问题追问；非正式矩阵。
- [Flash失败冒烟](../zhipu-glm-4.7-flash-smoke-2026-11-07.json)：历史请求失败，参数与后来的成功记录有差异，不能拼接为同条件稳定性统计。
- GLM-4.7：当前未找到成功响应证据；配置中的禁用状态不等于一次已发起的失败请求。

实际采访后，按[采访执行包](../../docs/guo-yuqi-interview-kit.md)另存匿名记录与公开图片，保留[空白模板](../guo-yuqi-interview-template.md)。当前没有受访者意见，所有P0/P1建议均为作者规划。
