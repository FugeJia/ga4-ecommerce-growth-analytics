# 数据契约与质量规则

源 schema 参见 [Google BigQuery Export schema](https://support.google.com/analytics/answer/7029846)。提取只用历史样例常见字段，不依赖新版本 batch_event_index 或 session_traffic_source_last_click。

| 归一化字段 | 类型 / 来源 | 处理 |
|---|---|---|
| event_date | DATE / event_date | 保留属性时区日期，必须有效 |
| event_ts | UTC timestamp / event_timestamp | 必须有效；会话内排序 |
| event_name | string | 小写 snake_case，必须有效 |
| user_key | string / user_pseudo_id | 占位/空值隔离并计数，不用于人级指标 |
| session_id | nullable integer / event_params.ga_session_id | 缺失计数、漏斗排除 |
| source / medium | string / traffic_source | 空与占位值归为 unknown；首获客维度 |
| device | string / device.category | 未知保留 unknown |
| transaction_id | nullable string / ecommerce.transaction_id | purchase 去重；占位 ID 视作缺失 |
| revenue_usd | nullable numeric / ecommerce.purchase_revenue_in_usd | 不用零补缺失，不是本币 |

## 强制规则

- 非空输入；必须包含全部 10 个字段；日期、时间、事件名可解析且非空。
- 金额与 session_id 必须可转换，不静默吞掉错误。
- 一个交易 ID 多个用户或多个不同非空金额 → 阻断，人工检查。
- build 必须有侧车来源清单且 SHA-256 与输入完全相符；合成/公开模式只能为已支持值。
- 目标构建目录已存在 → 拒绝覆盖；先在临时目录完整构建再发布。

## 报告而非硬阈值

重复归一化行、无效用户、缺失 session_id、purchase 缺少交易 ID、订单缺少收入/负收入分别计数。异常比例不自动声称低于 1%，也不因公开混淆样例里有这些情况就伪造“修复后达标”。

质量门禁证明的是程序输入符合约定，不是端到端埋点完整：要估计采集缺失，应将客户端/服务端发送日志与接收日志通过 event_id 对账，或用支付系统核对有效订单。样例里没有这些独立真值。来源清单是可追溯记录，不是加密签名或反篡改认证。

## 埋点设计交付

[24 项事件方案](../contracts/tracking-plan.csv) 是面向未来实现的设计，`verification_status=not_profiled` 表示尚未查询公开数据事件目录，不能称“已在 Google 站点部署”。公共属性建议 user_pseudo_id、可用时 user_id、session_id、event_id、source、medium、device、timestamp；本项目实际抽取字段按上表执行。不要将邮箱、电话、原始地址写入埋点。

命名规则：推荐事件沿用 GA4 名称；自定义事件使用小写 snake_case。实现时指定唯一 owner、触发位置、去重键、required 参数和验证查询。tracking-plan.csv 中的 sign_up/login 等即使为 GA4 推荐事件，也不意味着样例中存在。
