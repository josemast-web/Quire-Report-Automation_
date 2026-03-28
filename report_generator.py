"""
report_generator.py  –  Builds HTML email body and plain-text attachments.

All HTML uses inline styles for Gmail compatibility (no external CSS).
"""
import pandas as pd
from datetime import datetime, timezone, timedelta
import config
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# INLINE STYLE CONSTANTS  –  Gmail-safe
# ============================================================================
S_BODY      = "font-family: Helvetica, Arial, sans-serif; line-height: 1.6; color: #333333; background-color: #f4f4f4; margin: 0; padding: 0;"
S_CONTAINER = "max-width: 800px; margin: 0 auto; background-color: #ffffff; padding: 20px; border-radius: 8px;"
S_H1        = "color: #2c3e50; font-size: 24px; border-bottom: 3px solid #3498db; padding-bottom: 10px; margin-bottom: 20px;"
S_H2        = "color: #34495e; font-size: 18px; margin-top: 30px; border-bottom: 1px solid #eee; padding-bottom: 5px;"
S_META      = "background-color: #f8f9fa; padding: 15px; border-radius: 4px; color: #666; font-size: 12px; margin-bottom: 20px;"
S_TABLE     = "width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px;"
S_TH        = "background-color: #3498db; color: #ffffff; padding: 10px; text-align: left; font-weight: bold;"
S_TD        = "padding: 10px; border-bottom: 1px solid #eeeeee;"
S_CARD_TABLE = "width: 100%; border-collapse: separate; border-spacing: 10px; margin-top: 10px;"
S_CARD_TD   = "width: 33%; padding: 15px; border-radius: 6px; color: white; text-align: center; vertical-align: top;"
S_FOOTER    = "text-align: center; color: #999; font-size: 11px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;"

# Card colors
C_INFO    = "background-color: #3498db;"
C_SUCCESS = "background-color: #27ae60;"
C_WARN    = "background-color: #f39c12;"
C_DANGER  = "background-color: #c0392b;"
C_SEC     = "background-color: #7f8c8d;"


def generate_project_progress_table(df: pd.DataFrame) -> str:
    """Generate project progress table using inline-style HTML (Gmail safe)."""
    ids_objetivo = list(config.PROYECTOS_OBJETIVO.keys())
    df_summary   = df[df["project_id"].isin(ids_objetivo)].copy()

    if df_summary.empty:
        return (
            '<div style="padding:15px; background:#fee; color:#c0392b; border-radius:4px;">'
            "No target projects found.</div>"
        )

    proj_stats = df_summary.groupby("project_name").agg(
        Total_Tasks     =("id",           "count"),
        Completed_Tasks =("is_completed", "sum"),
        Total_Time_Log  =("hours_total",  "sum"),
        Time_Log_Empty  =("hours_total",  lambda x: (x == 0).sum()),
    ).reset_index()

    proj_stats["Pct_Completed"] = (
        proj_stats["Completed_Tasks"] / proj_stats["Total_Tasks"] * 100
    ).fillna(0).round(1)
    proj_stats = proj_stats.sort_values("Pct_Completed", ascending=False)

    rows_html = ""
    for idx, row in proj_stats.iterrows():
        bg  = "#f9f9f9" if idx % 2 == 0 else "#ffffff"
        pct = row["Pct_Completed"]

        bar_html = f"""
        <table cellspacing="0" cellpadding="0" style="width:100%; height:20px; background-color:#ecf0f1; border-radius:3px;">
            <tr>
                <td style="width:{pct}%; background-color:#27ae60; border-radius:3px; font-size:0; line-height:0;">&nbsp;</td>
                <td style="width:{100 - pct}%; font-size:0; line-height:0;">&nbsp;</td>
            </tr>
        </table>
        <div style="font-size:10px; color:#666; text-align:center;">{pct}%</div>
        """

        warn_style = "color:#c0392b; font-weight:bold;" if row["Time_Log_Empty"] > 0 else "color:#ccc;"

        rows_html += f"""
        <tr style="background-color:{bg};">
            <td style="{S_TD} font-weight:bold;">{row['project_name']}</td>
            <td style="{S_TD} text-align:center;">{row['Total_Tasks']}</td>
            <td style="{S_TD} text-align:center;">{row['Completed_Tasks']}</td>
            <td style="{S_TD} width:120px;">{bar_html}</td>
            <td style="{S_TD} text-align:center;">{row['Total_Time_Log']:.1f}h</td>
            <td style="{S_TD} text-align:center; {warn_style}">{row['Time_Log_Empty']}</td>
        </tr>
        """

    return f"""
    <table style="{S_TABLE}">
        <thead>
            <tr>
                <th style="{S_TH}">PROJECT</th>
                <th style="{S_TH} text-align:center;">TASKS</th>
                <th style="{S_TH} text-align:center;">DONE</th>
                <th style="{S_TH} width:120px;">PROGRESS</th>
                <th style="{S_TH} text-align:center;">HOURS</th>
                <th style="{S_TH} text-align:center;">NO LOG</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    """


def generate_staff_summary_table(df: pd.DataFrame) -> str:
    """Staff summary card layout (2 columns per row)."""
    if df.empty:
        return "<p>No staff data.</p>"

    cards_html  = ""
    staff_list  = config.SPECIAL_STAFF

    for i in range(0, len(staff_list), 2):
        row_staff   = staff_list[i:i + 2]
        cards_html += "<tr>"

        for person in row_staff:
            person_df = df[df["Assignee"] == person]
            h_w       = person_df["hours_week"].sum()
            h_m       = person_df["hours_month"].sum()
            tasks_w   = len(person_df[person_df.get("completed_this_week", False)])

            cards_html += f"""
            <td style="width:50%; padding:10px; vertical-align:top;">
                <div style="background-color:#f8f9fa; border-left:4px solid #3498db; padding:15px; border-radius:4px;">
                    <div style="font-size:16px; font-weight:bold; color:#2c3e50; margin-bottom:5px;">{person}</div>
                    <div style="font-size:12px; color:#555;">
                        <div style="margin-bottom:4px;"><strong>Week:</strong> {h_w:.1f}h <span style="color:#777;">({tasks_w} done)</span></div>
                        <div><strong>Month:</strong> {h_m:.1f}h</div>
                    </div>
                </div>
            </td>
            """
        cards_html += "</tr>"

    return f'<table style="width:100%; border-collapse:separate; border-spacing:0;">{cards_html}</table>'


def generate_kpi_table(df: pd.DataFrame, is_week: bool = True) -> str:
    """KPI summary cards in a 3-column table layout."""
    period_col = "active_week" if is_week else "active_month"
    col_time   = "hours_week"  if is_week else "hours_month"

    if period_col not in df.columns or df[df[period_col]].empty:
        return '<p style="font-style:italic; color:#999;">No activity data.</p>'

    df_filtered = df[df[period_col]]

    total_active = len(df_filtered)
    with_time    = len(df_filtered[df_filtered[col_time] > 0])
    completed    = len(df_filtered[df_filtered["is_completed"]])
    no_time_log  = len(df_filtered[(df_filtered[col_time] == 0) & df_filtered["is_completed"]])
    total_hours  = df_filtered[col_time].sum()
    avg_hours    = total_hours / total_active if total_active > 0 else 0

    return f"""
    <table style="{S_CARD_TABLE}">
        <tr>
            <td style="{S_CARD_TD} {C_INFO}">
                <div style="font-size:11px; opacity:0.9;">TOTAL ACTIVE</div>
                <div style="font-size:24px; font-weight:bold;">{total_active}</div>
            </td>
            <td style="{S_CARD_TD} {C_SUCCESS}">
                <div style="font-size:11px; opacity:0.9;">WITH TIME LOGS</div>
                <div style="font-size:24px; font-weight:bold;">{with_time}</div>
            </td>
            <td style="{S_CARD_TD} {C_SEC}">
                <div style="font-size:11px; opacity:0.9;">COMPLETED</div>
                <div style="font-size:24px; font-weight:bold;">{completed}</div>
            </td>
        </tr>
        <tr>
            <td style="{S_CARD_TD} {C_WARN}">
                <div style="font-size:11px; opacity:0.9;">DONE W/O LOG</div>
                <div style="font-size:24px; font-weight:bold;">{no_time_log}</div>
            </td>
            <td style="{S_CARD_TD} {C_INFO}">
                <div style="font-size:11px; opacity:0.9;">TOTAL HOURS</div>
                <div style="font-size:24px; font-weight:bold;">{total_hours:.1f}h</div>
            </td>
            <td style="{S_CARD_TD} {C_SEC}">
                <div style="font-size:11px; opacity:0.9;">AVG HOURS/TASK</div>
                <div style="font-size:24px; font-weight:bold;">{avg_hours:.1f}h</div>
            </td>
        </tr>
    </table>
    """


def create_txt_content(
    df_filtered: pd.DataFrame,
    title: str,
    start_date,
    end_date,
    is_week: bool = True,
) -> str:
    """Generate plain-text activity breakdown report."""
    col_hours = "hours_week" if is_week else "hours_month"
    lines = [f"{'=' * 60}", f"{title:^60}", f"{'=' * 60}"]
    lines.append(f"Period: {start_date} to {end_date}\n")

    if df_filtered.empty:
        lines.append("No activity recorded.")
        return "\n".join(lines)

    df_sorted = df_filtered.sort_values(
        by=["Assignee", "completed_at_parsed"], na_position="last"
    )

    for assignee, group in df_sorted.groupby("Assignee"):
        lines.append(f"\n>>> {assignee.upper()}")
        lines.append("-" * 60)

        total_h = 0
        for _, row in group.iterrows():
            h_val    = row[col_hours]
            total_h += h_val
            status   = "[DONE]" if row["is_completed"] else "[WIP] "
            date_str = (
                row["completed_at_parsed"].strftime("%Y-%m-%d")
                if pd.notna(row["completed_at_parsed"])
                else "In Progress"
            )
            lines.append(f"  {status} [{date_str}] {str(row['name'])[:50]}")
            lines.append(
                f"         {h_val}h | {row.get('project_name', 'N/A')} | {row.get('Tag', '')}"
            )

        lines.append("." * 60)
        lines.append(f"   Subtotal: {len(group)} tasks | {total_h:.1f} hours")

    return "\n".join(lines)


def generate_reports(df: pd.DataFrame) -> Tuple[str, str, str]:
    """
    Orchestrate report generation.

    Returns:
        Tuple of (html_report, txt_week_content, txt_month_content)
    """
    logger.info("Generating reports...")
    now = datetime.now(timezone.utc)

    # Date ranges
    days_to_last_monday = now.weekday() + 7
    last_monday         = (now - timedelta(days=days_to_last_monday)).date()
    last_friday         = last_monday + timedelta(days=4)
    one_month_ago       = now - timedelta(days=30)

    start_week  = pd.Timestamp(last_monday).tz_localize("UTC")
    end_week    = pd.Timestamp(last_friday).tz_localize("UTC").replace(hour=23, minute=59)
    start_month = pd.Timestamp(one_month_ago)

    # Activity flags
    df["completed_this_week"]  = (df["completed_at_parsed"] >= start_week) & (df["completed_at_parsed"] <= end_week)
    df["completed_this_month"] = df["completed_at_parsed"] >= start_month
    df["active_week"]          = (df["hours_week"] > 0) | df["completed_this_week"]
    df["active_month"]         = (df["hours_month"] > 0) | df["completed_this_month"]

    # Report label loaded from env var (no company name hard-coded)
    report_label = os.environ.get("REPORT_LABEL", "Automated Report Bot")

    html_report = f"""
    <!DOCTYPE html>
    <html>
    <body style="{S_BODY}">
    <div style="{S_CONTAINER}">
        <div style="{S_H1}">Project Status Report</div>

        <div style="{S_META}">
            <strong>Generated:</strong> {now.strftime('%Y-%m-%d %H:%M UTC')}<br>
            <strong>Week Period:</strong> {last_monday} to {last_friday}<br>
            <strong>Month Period:</strong> Last 30 days
        </div>

        <div style="{S_H2}">Project Progress</div>
        {generate_project_progress_table(df)}

        <div style="{S_H2}">Staff Performance</div>
        {generate_staff_summary_table(df)}

        <div style="{S_H2}">Weekly Statistics</div>
        {generate_kpi_table(df, is_week=True)}

        <div style="{S_H2}">Monthly Statistics</div>
        {generate_kpi_table(df, is_week=False)}

        <div style="{S_FOOTER}">
            Generated by {report_label}
        </div>
    </div>
    </body>
    </html>
    """

    txt_week  = create_txt_content(df[df["active_week"]],  "WEEKLY REPORT",  last_monday,           last_friday,     True)
    txt_month = create_txt_content(df[df["active_month"]], "MONTHLY REPORT", one_month_ago.date(),  now.date(),      False)

    return html_report, txt_week, txt_month


# Lazy import to avoid circular dep when called from generate_reports
import os
