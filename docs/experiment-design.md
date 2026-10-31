# 新客首次购买引导实验：预注册方案模板

这是未来实验设计，不是从 GA4 样例恢复的真实实验。样例没有随机分组、曝光或结果窗口的独立记录，不能证明改版产生提升。

- 假设：改善商品信息和首购引导可能提高新客 7 日购买率。
- 单位：稳定的匿名用户 ID；首次合格曝光前按固定 hash 50:50 分流，并保持组别不变。
- 人群：新客、指定支持平台；预先排除机器人/内部账号，不能按曝光后的行为筛人。
- 主要指标：随机化用户在首次曝光后 7×24 小时内是否至少一次有效购买，按 ITT，包含未实际交互用户。
- 护栏：页面错误率、加载延时、取消/退款率、收入/用户。护栏另行处理多重比较。
- 样本量：示例 baseline=20%、绝对 MDE=2 个百分点、α=.05 双侧、power=.8，使用正态近似；这些不是 GA4 实测基线。
- 周期：至少覆盖完整周，按样本量与流量预测决定截止日；等待全部结果窗口成熟，期间不按 p 值提前停止。
- 质量：唯一用户一行，分组不可变，无跨组污染；SRM 用 50:50 二项检验，p<.001 判 invalid_srm。
- 主检验：2×2 Pearson 卡方（不做连续性校正）；期望频数<5 时用双侧 Fisher exact。报告绝对/相对提升和 Newcombe-Wilson 差值置信区间。
- 决策：significant 只表示主指标统计显著，不自动意味着正向提升或应该上线；必须结合方向、区间、护栏、样本成熟和业务价值。

工具输入：CSV `user_key,variant,converted`，variant=control/treatment，converted=0/1，结果窗口在上传前计算成熟，程序无法从汇总 CSV 验证随机化或曝光合法性。

```python
import pandas as pd
from ga4_growth.statistics import sample_size, analyze_experiment
print(sample_size(.20, .02))
print(analyze_experiment(pd.read_csv('examples/experiment/synthetic_assignments.csv')))
```

合成实验示例用于复现计算，不用于简历宣称任何真实提升。[SciPy 卡方检验文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2_contingency.html)
