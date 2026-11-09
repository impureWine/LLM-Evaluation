# 庄剀涵（102400435）任务交付说明

交付日期：2026-11-09。适配团队仓库基线：`7d6e7c214459488d5310a2390cd9f0abbae3dd70`。

## 已完成的个人任务

| 分工要求 | 交付文件 | 完成内容 |
| --- | --- | --- |
| 固定车型数据及来源表 | [原始车型库](../configs/evaluation-v1.json)、[车型来源表](../data/vehicle-sources-v1.json) | 五款教学模拟车；年份、配置、价格口径、单位、来源日期与未知参数说明 |
| 至少三个购车场景 | [场景与脚本](../configs/scenario-rules-v1.json) | 城市通勤、家庭出行、周末跨城；各含预算和预算外硬约束 |
| 后续需求变更脚本 | 同上 | 第2轮新增L2、增加插电混动条件或替换预算；明确生效轮次和保留条件 |
| 满足约束的参考集合 | [参考答案](../data/reference-answers-v1.json) | 三场景十二轮完整可行集合、被替代条件、每辆不合格车型的原因 |
| 公共实验方法的数据部分 | [车型与场景报告](zhuang-kaihan-data-and-scenarios.md) | 数据边界、完整脚本、筛选逻辑、版本指纹与协作说明 |
| 市场规模、增长、直接及潜在用户 | [市场与商业报告](zhuang-kaihan-market-and-business.md) | 全球LLM/Agent市场、国内生成式AI用户、潜在客户口径与证据限制 |
| 商业模式资料 | 同上 | 智谱MaaS与按量计费、购车助手收费方式比较、完整任务成本公式 |
| 可核验资料 | [来源JSON](../data/market-sources-v1.json)、[短摘录](../evidence/market-source-excerpts-2026-11-09.md) | 七个来源（含作业原文）、访问日期、统计时期、短摘录、原始页面指纹 |
| 校验代码及版本 | [校验模块](../src/llm_eval/dataset.py)、[测试](../tests/test_dataset.py)、[版本指纹](../data/release-v1.json) | 离线参考计算、脚本一致性、答案隔离、来源和版本漂移检查 |

个人正文可直接从两份报告中取用；已将公共方法、商业分析、市场概况摘要加入[博客整合稿](evaluation-blog.md)，并更新[分工进度](evaluation-coordination.md)的本人条目。

## 复现

在仓库根目录执行，Python 3.8+，无需 API Key 或第三方依赖：

```powershell
$env:PYTHONPATH = 'src'
python -m llm_eval.dataset
python -m llm_eval.evaluate --dry-run
python -m unittest discover -s tests -v
```

第一条命令报告5款车、3场景、12轮核验通过，且 `api_calls=0`。第二条显示计划18个四轮任务、零实际API调用。全部34项离线测试通过，其中10项为本次新增的数据合同回归测试。执行证据见[数据校验](../evidence/data-validation-2026-11-09.json)、[运行预检](../evidence/zhuang-kaihan-dry-run-2026-11-09.json)及[测试输出](../evidence/zhuang-kaihan-tests-2026-11-09.txt)。

## 合入与冻结说明

本次沿用原车型和运行输入，新增侧边元数据、规则及参考集合。正式数据冻结仍需要团队记录实际合入提交和审核结果；`release-v1.json` 的 `prepared_for_team_freeze` 是材料状态。已有模型正式日志不能因为材料补齐就追溯声明为已冻结。

合入时保留队友的新改动，尤其是 README、进度和博客三个共享文档中的内容。若团队主分支已前进，优先应用随附补丁并检查冲突，不直接覆盖整个仓库。新增数据文件变更后先检查影响，再显式更新参考答案和指纹。

这里没有新增真实模型调用、伪造实验结果、代替其他成员的采访或评分案例，也没有发布博客或替团队提交作业。已知资料限制包括纯API市场收入和精确平台客户数尚无可核验统计；正文已用明确口径的LLM整体市场、Agent市场及CNNIC品类用户资料支持分析。
