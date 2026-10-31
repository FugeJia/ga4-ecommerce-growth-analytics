"""Run: streamlit run app.py -- --input data/demo/events.parquet"""

import argparse
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ga4_growth.provenance import verify_input
from ga4_growth.statistics import analyze_experiment, detect_anomalies, sample_size
from ga4_growth.warehouse import Warehouse

st.set_page_config(page_title="GA4 Growth Lab", page_icon="📊", layout="wide")
parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, default=Path("data/demo/events.parquet"))
args, _ = parser.parse_known_args()
st.title("GA4 Growth Lab · 电商增长分析")
if not args.input.exists():
    st.info("先运行 ga4 demo，再启动看板。详见 README。")
    st.stop()


@st.cache_data
def load(path, modified, sidecar_modified):
    provenance = verify_input(Path(path))
    return pd.read_parquet(path), provenance


sidecar = args.input.with_suffix(".manifest.json")
try:
    frame, provenance = load(
        str(args.input),
        args.input.stat().st_mtime_ns,
        sidecar.stat().st_mtime_ns if sidecar.exists() else 0,
    )
except ValueError as error:
    st.error(str(error))
    st.stop()
mode = provenance["data_mode"]
if mode == "synthetic_demo":
    st.warning("SYNTHETIC DEMO · 当前为固定随机种子的合成演示数据，所有数值仅用于验收功能。")
elif mode == "bigquery_public":
    st.info("BIGQUERY PUBLIC · Google 历史混淆样例；结果不代表当前真实经营表现。")
else:
    st.error("缺少可信数据来源标记，请使用 ga4 demo / ga4 extract 生成输入。")
    st.stop()
st.caption(
    "访问用户 ≠ GA4 界面活跃用户定义；渠道为首次获客 source / medium；金额为 USD 购买收入，未扣退款。"
)
frame["event_date"] = pd.to_datetime(frame.event_date).dt.date
with st.sidebar:
    st.header("分析范围")
    dates = st.date_input(
        "日期范围",
        (frame.event_date.min(), frame.event_date.max()),
        min_value=frame.event_date.min(),
        max_value=frame.event_date.max(),
    )
    sources = st.multiselect("首次获客来源", sorted(frame.source.dropna().unique()))
    devices = st.multiselect("设备类型", sorted(frame.device.dropna().unique()))
    st.caption(
        "空选表示全部。留存的日期筛选限定获客 cohort，回访观察到数据末日。RFM 使用筛选日期内订单。"
    )
if len(dates) != 2:
    st.info("请选择开始和结束日期。")
    st.stop()
start, end = dates
dimension_frame = frame
if sources:
    dimension_frame = dimension_frame[dimension_frame.source.isin(sources)]
if devices:
    dimension_frame = dimension_frame[dimension_frame.device.isin(devices)]
selected = dimension_frame[dimension_frame.event_date.between(start, end)]
if selected.empty:
    st.info("当前筛选无事件。")
    st.stop()
try:
    warehouse = Warehouse(selected)
except ValueError as error:
    st.error(f"数据质量门禁未通过：{error}")
    st.stop()
try:
    daily = detect_anomalies(warehouse.daily())
    funnel = warehouse.funnel()
    orders = warehouse.query("SELECT * FROM orders")
    users = int(warehouse.query("SELECT count(DISTINCT user_key) FROM events").iloc[0, 0])
    buyers = int(
        warehouse.query(
            "SELECT count(DISTINCT user_key) FROM events WHERE event_name='purchase'"
        ).iloc[0, 0]
    )
    metrics = st.columns(4)
    for col, label, value in zip(
        metrics,
        ["访问用户", "购买用户转化率", "去重订单", "购买收入 USD"],
        [
            f"{users:,}",
            f"{buyers / users:.2%}",
            f"{len(orders):,}",
            f"${orders.revenue_usd.sum(min_count=1):,.2f}",
        ],
    ):
        col.metric(label, value)
    tabs = st.tabs(["概览 / 监控", "转化漏斗", "同期群留存", "RFM 分层", "实验设计", "数据质量"])
    with tabs[0]:
        st.plotly_chart(
            px.line(daily, x="event_date", y="dau", title="每日访问用户"), use_container_width=True
        )
        st.plotly_chart(
            px.line(daily, x="event_date", y="purchase_cvr", title="每日购买用户 / 每日访问用户"),
            use_container_width=True,
        )
        st.caption(
            "3σ：仅使用之前 28 天，至少 14 天；转化率告警要求当日 DAU≥100。属探索性规则，未经季节性校正。"
        )
        alerts = daily[daily.dau_alert | daily.purchase_cvr_alert]
        st.dataframe(alerts, use_container_width=True)
        st.download_button(
            "下载每日指标 CSV", daily.to_csv(index=False).encode(), "daily.csv", "text/csv"
        )
    with tabs[1]:
        columns = ["view_item", "add_to_cart", "begin_checkout", "purchase"]
        counts = funnel[columns].sum()
        st.plotly_chart(
            go.Figure(go.Funnel(y=columns, x=counts.values, textinfo="value+percent initial")),
            use_container_width=True,
        )
        st.caption(
            "闭合会话漏斗，后一步时间戳必须严格大于前一步；并列时间戳不推断顺序。购买阶段是事件到达，不等同去重订单数。"
        )
        st.dataframe(funnel, use_container_width=True)
    with tabs[2]:
        history = Warehouse(dimension_frame)
        try:
            retention = history.retention(start, end, observation_end=frame.event_date.max())
        finally:
            history.close()
        pivot = retention.pivot(index="cohort_week", columns="horizon", values="retention_rate")
        if not pivot.empty:
            pivot.columns = [f"D{h}" for h in pivot.columns]
            pivot.index = pivot.index.strftime("%Y-%m-%d")
            st.plotly_chart(
                px.imshow(
                    pivot,
                    text_auto=".1%",
                    aspect="auto",
                    title="按周汇总的精确 D1 / D7 / D30 留存",
                    labels=dict(x="距首次访问天数", y="Cohort 周", color="留存率"),
                    zmin=0,
                    zmax=1,
                ),
                use_container_width=True,
            )
        st.caption(
            "仅 first_visit 用户入组；按用户实际获客日判断观察资格。未成熟为 NULL；设备筛选后仅统计同类设备上的回访。"
        )
        st.dataframe(retention, use_container_width=True)
    with tabs[3]:
        rfm = warehouse.rfm()
        if not rfm.empty:
            st.plotly_chart(
                px.bar(
                    rfm.groupby("segment").size().rename("users").reset_index(),
                    x="segment",
                    y="users",
                    title="购买用户运营分层",
                ),
                use_container_width=True,
            )
        st.caption(
            "以当前筛选范围末个观察日为快照；仅评分收入完整且非负的购买用户。用户 ID 仅本地导出，不写入公开仓库。"
        )
        st.dataframe(rfm, use_container_width=True)
        st.download_button(
            "下载本地分层名单", rfm.to_csv(index=False).encode(), "rfm.csv", "text/csv"
        )
    with tabs[4]:
        st.info("原始数据没有随机分组和实验曝光，本模块提供方法工具，不生成“真实改版提升”结论。")
        baseline = st.number_input("基线转化率", min_value=0.001, max_value=0.95, value=0.2)
        mde = st.number_input(
            "绝对 MDE（.02 = 2 个百分点）",
            min_value=0.001,
            max_value=float(round(1 - baseline - 0.001, 6)),
            value=0.02,
        )
        st.metric("每组所需样本（α=.05，power=.8）", f"{sample_size(baseline, mde):,}")
        st.caption(
            "50:50、双侧、独立用户、固定样本检验。样本量为正态近似；须另评估曝光率、延迟与流失。"
        )
        uploaded = st.file_uploader("上传用户级实验 CSV：user_key, variant, converted", type="csv")
        if uploaded is not None:
            try:
                st.json(analyze_experiment(pd.read_csv(uploaded)))
            except ValueError as error:
                st.error(str(error))
    with tabs[5]:
        st.json(warehouse.quality)
        st.caption("检查的是已收到事件的字段完整性与一致性，不能估计未被采集的事件缺失率。")
finally:
    warehouse.close()
