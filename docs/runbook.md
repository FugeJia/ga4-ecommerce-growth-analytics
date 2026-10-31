# 运行与维护

## 环境、复现与失败处理

Python 3.12、venv、requirements.lock。依赖快照固定直接和间接包版本，pip 校验包元数据约束；不是带文件 hash 的供应链锁文件，版本变更应重新安装、测试和检查 CI。Linux 专属 watchdog 通过 marker 固定。

输入 Parquet 同目录必须有同名 `.manifest.json`。合成数据带 seed；公开数据带查询 hash 和 BigQuery job_id。构建先校验输入 hash，生成全部文件到临时目录，成功后 rename 到新目标。失败不会替换已有输出。源文件写入中断时可能留半成品，使用新目录重试并检查侧车，不强制覆盖。

常见问题：

| 故障 | 处理 |
|---|---|
| DefaultCredentialsError | gcloud auth application-default login；不把密钥提交到 Git |
| Access Denied / API 未开启 | 检查 project、BigQuery API 和 jobs.create 权限 |
| 扫描量超 cap | 先缩短日期验证，再显式调整 --max-bytes |
| 交易 ID 冲突 | 检查冲突来源，混淆数据可能不一致；不静默合并多个用户 |
| 输入 hash 不匹配 | 从原始输入重建，检查来源；不要为了通过检查随意改清单 |
| 目标已存在 | 使用新版本目录；确认旧数据不再需要后再人工删除 |
| 留存为空 | 是否包含 first_visit、观察期够长、筛选是否太窄 |
| 看板空白 | 使用源 Parquet，不能把 marts CSV 作为 --input |

## 运行产物

- daily.csv：日历日访问用户、买家、订单、USD 收入、监控基线和告警。
- funnel.csv：source×medium×device×user_type 的会话漏斗。
- retention.csv：cohort_week×horizon，成熟分母与回访人数。
- rfm.csv：用户级 R/F/M 与 segment，只存本地。
- quality.json：输入质量计数。
- manifest.json：来源模式、输入 hash、观察期、指标版本、构建时间。
- report.md：可供检查的运行摘要。

本仓库示例只复制 synthetic_demo 的聚合产物；不复制用户级 rfm.csv。生成时间为实际 UTC 时间，不手工伪造。指标代码版本为 package/metrics_version；源码版本由 Git commit 和 CI run 追溯，当前不自动填充 git_sha（可能为 null）。

## 生产化差距与迁移

当前抽取调用 to_dataframe，一次加载全部规范化事件；DuckDB 内存库也会复制数据。无针对全周期大小的负载基准。首次接入先跑一天，观察内存，再扩大范围。超过单机能力时把 SQL marts 下推 BigQuery，使用分区表/dbt，Parquet 只下载聚合结果。

当前没有自动调度、增量 watermark、在线 SLA 或上线告警；CI 验证代码与合成数据，不查询真实数据。接入真实环境时应补：

- 分区级 freshness 和覆盖检查、event_id 幂等；GA4 延迟更新需回看历史分区。
- 区分事件时点与订单结算，退款/税费/运费对账，真实用户身份策略。
- Orchestrator 重试、可观察 job 状态、权限最小化、故障 owner、数据访问审计。
- 周期性基线与控制图、实验曝光与成熟窗口对账、告警人工复核。

回滚：保留旧版本输出目录和源码 tag，重新启动应用时显式传入对应输入文件。新指标版本不要覆盖旧观察结果。
