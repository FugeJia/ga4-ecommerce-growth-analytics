# Tableau 接入与版式

当前已实现的是 Streamlit。以下是可复现的 Tableau 制作指南，没有已发布工作簿或 Tableau Public 链接。

1. 从构建目录分别连接 daily.csv / funnel.csv / retention.csv / rfm.csv，使用四个独立数据源。不要按日期直接把四表横向连接，避免多对多放大。
2. 总览：日期序列、SUM(orders)、SUM(revenue_usd)、日 DAU 折线。daily.dau 不可 SUM 成周期去重用户；周期去重用户请从事件明细重算或使用 Streamlit KPI。
3. 漏斗：先按 source/medium/device 过滤，再 SUM 各阶段会话数。funnel.csv 为整次构建结果，没有日粒度，日期筛选需用所选范围重建或使用 Streamlit。
4. 留存：cohort_week 为行、horizon 为列，颜色使用 SUM(retained_users)/SUM(eligible_users)。分母为 0 保持 NULL。不要平均行留存率。
5. RFM：segment 条形图，用户数 count；M 用 USD，标注 snapshot 日期和观察窗口。真实 user_key 不发布到公共 BI，只发布汇总。

建议画布 1440×1000：顶部标题/数据模式/观察期，第二行四项 KPI，中部趋势与漏斗，底部留存热力图及分层条形图。使用蓝色主色、橙色异常、灰色未知。筛选作用范围写在每张图旁边。

若使用 Tableau Public，只上传已明确标注的合成聚合数据；Google 原始用户标识及本地 RFM 名单不随作品集公开。
