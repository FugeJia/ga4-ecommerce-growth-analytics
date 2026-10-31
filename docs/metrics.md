# 指标定义与分析边界

## 数据粒度与时间

event_date 保留 GA4 属性时区的日历日期；event_ts 为 UTC 时间，只用于事件排序。不能用 UTC 日期替换 event_date。数据末日来自实际导出最大 event_date；如果导出末日缺失，观察资格会保守缩短。采集日缺失与真实零活动无法仅凭导出事件区分，应结合源表完整性核对。

归一化层保留 11 个字段，完全相同的归一化行视为重复并去重。这是工程上的去重约定，不是源系统精确 event_id；原始上下文不同但选中字段相同的事件也可能被合并，因此不用于宣称精确原始事件量。

## 漏斗

漏斗按会话内有序行为计数，session_start 事件不是必需条件；键是 user_key + session_id。没有 session_id 的事件保留用于用户/订单分析，但不进入漏斗。闭合漏斗允许阶段之间有其他事件、不限制相邻事件、只在同会话推进。重复 view_item 后仍会从第一个 view_item 寻找之后的 cart，再找之后 checkout/purchase。

第一步通过率以 view_item 为分母；相邻步骤转化率 = next / previous。它与“范围内购买用户/范围内访问用户”、去重交易订单数是三个不同口径。渠道/设备是会话首次观察属性；切片截断跨边界会话，不能将每日截断漏斗简单求和当作完整周期漏斗。

漏斗包含 user_type：当天存在 first_visit 为 new_observed；存在更早观察日事件为 returning_observed；其余为 unknown。它按查询输入可见证据分类，不把窗口里首次出现的人都叫新客。日期/设备切片可能让原本有历史证据的用户变为 unknown。daily.new_users 只表示当日实际观测到 first_visit 的用户。

## 留存

cohort_date = 每个用户实际观察到的最早 first_visit 日期。仅 page_view 而无 first_visit 的用户不纳入获客 cohort。不同浏览器标识视为不同用户，不做跨设备归一。

- eligible(D) = cohort_date + D ≤ observation_end 的用户数。
- retained(D) = eligible 用户中在恰好第 D 天有任意事件的用户数。
- retention(D) = retained / eligible；分母为零输出 NULL。
- cohort_week = cohort_date 所在周的周一。

批处理对全输入计算。看板日期过滤 cohort 的入组日，回访一直观察到导出末日；来源、设备过滤作用于事件，因此设备筛选后衡量的是在相同设备类别内回访。可见 cohort 首日之前的历史缺失、first_visit 事件重复和混淆均影响解释。

## RFM 与运营策略

购买事件要求有效 transaction_id；一个 transaction_id 跨用户或出现不同非空金额时阻断整个构建。相同交易的重复回传按最新时间取一行。USD 收入为 purchase_revenue_in_usd，不把本币 value 直接相加。缺失收入不补成零；任何订单收入缺失或为负的买家均不评分。refund 事件未净额化，M 不是利润、净 GMV 或财务收入。

| 分层 | 规则（按优先级） | 可提出的运营假设 |
|---|---|---|
| high_value | R≤30 且 F≥2 且 M≥100 USD | 忠诚计划，控制补贴与打扰 |
| potential | 其他 R≤30 的合格买家 | 补充购前信息，测试复购推荐 |
| dormant | 30<R≤60 | 在合法可触达条件下测试召回 |
| lapsed | R>60 | 低频召回，使用随机 holdout 检验增量 |

这些是可解释的业务阈值，不是数据拟合的最优策略。F/M 只反映当前抽取及看板筛选窗口内已观察订单，不是全生命周期。名单仅模拟用途，没有可直接联系的客户信息，也未发送任何运营消息。

## 异常监控

DAU 和日购买用户率使用前 28 个日历日均值/样本标准差，至少 14 个历史点，|z|>3 标记。标准差为 0 时不评分。转化率额外要求当日 DAU≥100，比例型指标仍需二项模型或控制图进一步验证。WoW = DAU / 7 日前 DAU - 1；零分母为 NULL。没有足够年度数据，不实现同比。

日历补齐只覆盖输入 min/max 日期，空日 dau/orders 记零、cvr 为 NULL、收入无已知观测为 NULL。3σ 不校正星期/节假日、不控制多重比较，不应触发自动业务动作。渠道拆分只提供描述性调查线索，不等于因果归因；本数据没有可依赖的 App 版本改版记录。
