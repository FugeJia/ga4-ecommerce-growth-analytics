"""Regenerate committed synthetic aggregates; never copy raw or user-level public data."""

import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from ga4_growth.cli import save_input
from ga4_growth.demo import generate_demo
from ga4_growth.pipeline import build
from ga4_growth.statistics import analyze_experiment, sample_size
from ga4_growth.warehouse import Warehouse


def main():
    output = Path("examples/demo")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        source = folder / "events.parquet"
        frame = generate_demo()
        save_input(
            frame, source, {"data_mode": "synthetic_demo", "seed": 42, "source": "seeded_generator"}
        )
        build(source, folder / "marts")
        for name in [
            "daily.csv",
            "funnel.csv",
            "retention.csv",
            "quality.json",
            "manifest.json",
            "report.md",
        ]:
            shutil.copy(folder / "marts" / name, output / name)
        w = Warehouse(frame)
        try:
            funnel = w.funnel()[["view_item", "add_to_cart", "begin_checkout", "purchase"]].sum()
            rfm = w.rfm().groupby("segment").size()
            retention = w.retention().groupby("horizon")[["retained_users", "eligible_users"]].sum()
            lines = [
                "# 合成演示分析报告",
                "",
                "**SYNTHETIC DEMO — 不是真实 GA4 经营分析，也不支持因果结论。**",
                "",
                "此报告由 `python scripts/refresh_examples.py` 计算生成。生成器预设了设备路径概率；"
                "任何差异只能验证分析流程，不能用来选择真实业务方案。",
                "",
                "## 1. 会话漏斗",
                "",
                "| 阶段 | 会话数 | 相邻阶段转化率 |",
                "|---|---:|---:|",
            ]
            previous = None
            losses = []
            for stage, count in funnel.items():
                rate = f"{count / previous:.2%}" if previous else "—"
                lines.append(f"| {stage} | {count:,} | {rate} |")
                if previous:
                    losses.append((1 - count / previous, stage))
                previous = count
            worst = max(losses)
            lines += [
                "",
                f"相对流失最多的是进入 `{worst[1]}` 的步骤（流失 {worst[0]:.2%}）。"
                "这只反映演示生成器设定，真实业务还需页面、商品、价格和可用性证据。",
                "",
                "## 2. 精确日留存",
                "",
                "| Horizon | 成熟用户 | 回访用户 | 留存 |",
                "|---|---:|---:|---:|",
            ]
            for h, row in retention.iterrows():
                lines.append(
                    f"| D{h} | {int(row.eligible_users):,} | {int(row.retained_users):,} | "
                    f"{row.retained_users / row.eligible_users:.2%} |"
                )
            lines += [
                "",
                "先按用户实际获客日检查成熟资格，再跨 cohort 周加权；未成熟不按未留存处理。",
                "",
                "## 3. 购买用户分层",
                "",
                "| 分层 | 合格买家 |",
                "|---|---:|",
            ]
            for segment, count in rfm.items():
                lines.append(f"| {segment} | {count} |")
            lines += [
                "",
                "四类名单基于观察窗口内订单；非购买者、收入缺失或负收入买家不在评分名单。",
                "",
                "## 4. 下一步可验证的问题",
                "",
                "1. 真实查询先 profile 事件目录、字段缺失、session 覆盖率和交易冲突，再决定是否可分析。",
                "2. 按设备/来源/新老与未知分层比较漏斗，记录分母和不确定性，不直接把差异当原因。",
                "3. 若确认存在商品浏览到加购的问题，结合可用性观察设计改版实验，再按预注册方案验证。",
                "4. 对异常告警先检查源表完整性、星期和节假日，再检查渠道构成变化；不做自动上线。",
            ]
            (output / "analysis.md").write_text("\n".join(lines) + "\n")
        finally:
            w.close()
    experiment = Path("examples/experiment")
    experiment.mkdir(parents=True, exist_ok=True)
    assignments = pd.DataFrame(
        dict(
            user_key=[f"synthetic-{i}" for i in range(2000)],
            variant=["control"] * 1000 + ["treatment"] * 1000,
            converted=[1] * 200 + [0] * 800 + [1] * 225 + [0] * 775,
        )
    )
    assignments.to_csv(experiment / "synthetic_assignments.csv", index=False)
    (experiment / "result.json").write_text(
        json.dumps(
            dict(
                data_mode="synthetic_demo",
                planned_n_per_arm_example=sample_size(0.2, 0.02),
                analysis=analyze_experiment(assignments),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
