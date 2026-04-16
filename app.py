import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Aged Debtors Dashboard", layout="wide")

st.title("Aged Debtors Dashboard")
st.caption("Quick dashboard built from the raw aged debt export")

BUCKETS = [
    "Sum of 0-29 days",
    "Sum of 30-59 days",
    "Sum of 60-89 days",
    "Sum of 90-180 days",
    "Sum of 181 - 365 days",
    "Sum of >365 days",
]

BUCKET_LABELS = {
    "Sum of 0-29 days": "0-29 days",
    "Sum of 30-59 days": "30-59 days",
    "Sum of 60-89 days": "60-89 days",
    "Sum of 90-180 days": "90-180 days",
    "Sum of 181 - 365 days": "181-365 days",
    "Sum of >365 days": ">365 days",
}

REQUIRED_COLUMNS = [
    "Date",
    "Executive Directorate",
    "Directorate",
    "Service",
    "Sovservice",
    "Count of Total Balance Outstanding",
    "Sum of Total Balance Outstanding2",
    "Risk Debt",
    "Year",
    "Quarter",
] + BUCKETS


def load_data(uploaded_file) -> pd.DataFrame:
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file, sheet_name="Aged Debtor Reports")
    else:
        df = pd.read_excel("Aged Debtors Analysis.xlsx", sheet_name="Aged Debtor Reports")

    df = df.copy()
    df.columns = [str(c).strip() if c is not None else "" for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    numeric_cols = [
        "Count of Total Balance Outstanding",
        "Sum of Total Balance Outstanding2",
        "Risk Debt",
        *BUCKETS,
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["Quarter"] = df["Quarter"].astype(str)
    df["Period"] = pd.PeriodIndex(df["Date"], freq="Q").astype(str)
    df["Over 90 days"] = (
        df["Sum of 90-180 days"]
        + df["Sum of 181 - 365 days"]
        + df["Sum of >365 days"]
    )
    df["Over 180 days"] = df["Sum of 181 - 365 days"] + df["Sum of >365 days"]

    return df


@st.cache_data
def prepare_views(df: pd.DataFrame):
    period_summary = (
        df.groupby(["Date", "Period"], as_index=False)
        .agg(
            total_outstanding=("Sum of Total Balance Outstanding2", "sum"),
            risk_debt=("Risk Debt", "sum"),
            balances=("Count of Total Balance Outstanding", "sum"),
            overdue_90=("Over 90 days", "sum"),
            overdue_180=("Over 180 days", "sum"),
            bucket_0_29=("Sum of 0-29 days", "sum"),
            bucket_30_59=("Sum of 30-59 days", "sum"),
            bucket_60_89=("Sum of 60-89 days", "sum"),
            bucket_90_180=("Sum of 90-180 days", "sum"),
            bucket_181_365=("Sum of 181 - 365 days", "sum"),
            bucket_365_plus=("Sum of >365 days", "sum"),
        )
        .sort_values("Date")
    )

    period_summary["risk_pct"] = np.where(
        period_summary["total_outstanding"] != 0,
        period_summary["risk_debt"] / period_summary["total_outstanding"],
        0,
    )
    period_summary["overdue_90_pct"] = np.where(
        period_summary["total_outstanding"] != 0,
        period_summary["overdue_90"] / period_summary["total_outstanding"],
        0,
    )

    bucket_long = df.melt(
        id_vars=["Date", "Period", "Executive Directorate", "Directorate", "Service", "Sovservice"],
        value_vars=BUCKETS,
        var_name="Age Bucket",
        value_name="Value",
    )
    bucket_long["Age Bucket"] = bucket_long["Age Bucket"].map(BUCKET_LABELS)

    service_summary = (
        df.groupby(["Date", "Period", "Executive Directorate", "Directorate", "Service"], as_index=False)
        .agg(
            total_outstanding=("Sum of Total Balance Outstanding2", "sum"),
            risk_debt=("Risk Debt", "sum"),
            overdue_90=("Over 90 days", "sum"),
            overdue_180=("Over 180 days", "sum"),
            balances=("Count of Total Balance Outstanding", "sum"),
        )
    )
    service_summary["risk_pct"] = np.where(
        service_summary["total_outstanding"] != 0,
        service_summary["risk_debt"] / service_summary["total_outstanding"],
        0,
    )

    return period_summary, bucket_long, service_summary


def fmt_currency(value: float) -> str:
    return f"£{value:,.0f}"


def fmt_pct(value: float) -> str:
    return f"{value:.1%}"


with st.sidebar:
    st.header("Data")
    uploaded_file = st.file_uploader("Upload aged debt workbook", type=["xlsx"])
    st.caption("If no file is uploaded, the app will try to use Aged Debtors Analysis.xlsx in the app folder.")

try:
    df = load_data(uploaded_file)
except Exception as e:
    st.error(f"Could not load the workbook: {e}")
    st.stop()

period_summary, bucket_long, service_summary = prepare_views(df)

with st.sidebar:
    st.header("Filters")
    dates = sorted(df["Date"].dropna().unique())
    selected_date = st.selectbox(
        "Snapshot date",
        dates,
        index=len(dates) - 1 if dates else 0,
        format_func=lambda x: pd.to_datetime(x).strftime("%d %b %Y"),
    )

    exec_dirs = sorted(df["Executive Directorate"].dropna().unique().tolist())
    selected_exec = st.multiselect("Executive Directorate", exec_dirs, default=exec_dirs)

    directorates = sorted(
        df.loc[df["Executive Directorate"].isin(selected_exec), "Directorate"].dropna().unique().tolist()
    )
    selected_directorates = st.multiselect("Directorate", directorates, default=directorates)

filtered = df[
    (df["Date"] == pd.to_datetime(selected_date))
    & (df["Executive Directorate"].isin(selected_exec))
    & (df["Directorate"].isin(selected_directorates))
].copy()

if filtered.empty:
    st.warning("No data matches the current filters.")
    st.stop()

current_total = filtered["Sum of Total Balance Outstanding2"].sum()
current_risk = filtered["Risk Debt"].sum()
current_balances = filtered["Count of Total Balance Outstanding"].sum()
current_over90 = filtered["Over 90 days"].sum()
current_over180 = filtered["Over 180 days"].sum()
current_risk_pct = current_risk / current_total if current_total else 0
current_over90_pct = current_over90 / current_total if current_total else 0

prior_periods = period_summary.loc[period_summary["Date"] < pd.to_datetime(selected_date)].sort_values("Date")
prev_total = prior_periods.iloc[-1]["total_outstanding"] if not prior_periods.empty else None
prev_risk = prior_periods.iloc[-1]["risk_debt"] if not prior_periods.empty else None

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total outstanding", fmt_currency(current_total), None if prev_total is None else fmt_currency(current_total - prev_total))
col2.metric("Risk debt", fmt_currency(current_risk), None if prev_risk is None else fmt_currency(current_risk - prev_risk))
col3.metric("Risk %", fmt_pct(current_risk_pct))
col4.metric("Over 90 days", fmt_currency(current_over90), fmt_pct(current_over90_pct))
col5.metric("No. balances", f"{int(current_balances):,}")

st.markdown("### Headlines")
headlines = []
if current_risk_pct >= 0.5:
    headlines.append(f"Risk debt is high at {fmt_pct(current_risk_pct)} of total outstanding.")
if current_over90_pct >= 0.4:
    headlines.append(f"{fmt_pct(current_over90_pct)} of debt is over 90 days old, indicating recovery risk.")
if prev_total is not None and current_total > prev_total:
    headlines.append(f"Total outstanding has increased by {fmt_currency(current_total - prev_total)} since the previous snapshot.")
if prev_risk is not None and current_risk > prev_risk:
    headlines.append(f"Risk debt has increased by {fmt_currency(current_risk - prev_risk)} since the previous snapshot.")
if not headlines:
    headlines.append("No obvious adverse movement is flagged from the currently selected snapshot.")
for item in headlines[:4]:
    st.write(f"- {item}")

left, right = st.columns((1.3, 1))

with left:
    st.markdown("### Ageing profile")
    bucket_totals = pd.DataFrame({
        "Age Bucket": [BUCKET_LABELS[b] for b in BUCKETS],
        "Value": [filtered[b].sum() for b in BUCKETS],
    })
    fig_age = px.bar(
        bucket_totals,
        x="Age Bucket",
        y="Value",
        text_auto=".2s",
    )
    fig_age.update_layout(yaxis_title="Debt value (£)", xaxis_title="")
    st.plotly_chart(fig_age, use_container_width=True)

with right:
    st.markdown("### Risk vs total over time")
    trend_filtered = period_summary.copy()
    if selected_exec:
        mask = df["Executive Directorate"].isin(selected_exec)
        if selected_directorates:
            mask &= df["Directorate"].isin(selected_directorates)
        trend_filtered = (
            df.loc[mask]
            .groupby(["Date", "Period"], as_index=False)
            .agg(
                total_outstanding=("Sum of Total Balance Outstanding2", "sum"),
                risk_debt=("Risk Debt", "sum"),
            )
            .sort_values("Date")
        )
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(x=trend_filtered["Date"], y=trend_filtered["total_outstanding"], mode="lines+markers", name="Total outstanding"))
    fig_trend.add_trace(go.Scatter(x=trend_filtered["Date"], y=trend_filtered["risk_debt"], mode="lines+markers", name="Risk debt"))
    fig_trend.update_layout(yaxis_title="£", xaxis_title="")
    st.plotly_chart(fig_trend, use_container_width=True)

st.markdown("### Age bucket mix over time")
bucket_time = (
    bucket_long[
        (bucket_long["Date"].notna())
        & (bucket_long["Executive Directorate"].isin(selected_exec))
        & (bucket_long["Directorate"].isin(selected_directorates))
    ]
    .groupby(["Date", "Age Bucket"], as_index=False)["Value"]
    .sum()
)
fig_stack = px.bar(
    bucket_time,
    x="Date",
    y="Value",
    color="Age Bucket",
)
fig_stack.update_layout(yaxis_title="Debt value (£)", xaxis_title="")
st.plotly_chart(fig_stack, use_container_width=True)

left2, right2 = st.columns((1.05, 1.15))

with left2:
    st.markdown("### Top services by overdue debt")
    top_services = (
        filtered.groupby("Service", as_index=False)
        .agg(
            total_outstanding=("Sum of Total Balance Outstanding2", "sum"),
            overdue_90=("Over 90 days", "sum"),
            risk_debt=("Risk Debt", "sum"),
        )
        .sort_values("overdue_90", ascending=False)
        .head(15)
    )
    fig_top = px.bar(
        top_services.sort_values("overdue_90", ascending=True),
        x="overdue_90",
        y="Service",
        orientation="h",
        text_auto=".2s",
    )
    fig_top.update_layout(xaxis_title="Over 90 days (£)", yaxis_title="")
    st.plotly_chart(fig_top, use_container_width=True)

with right2:
    st.markdown("### Heatmap: service risk %")
    heatmap_df = (
        filtered.groupby(["Directorate", "Service"], as_index=False)
        .agg(
            total_outstanding=("Sum of Total Balance Outstanding2", "sum"),
            risk_debt=("Risk Debt", "sum"),
        )
    )
    heatmap_df["risk_pct"] = np.where(
        heatmap_df["total_outstanding"] != 0,
        heatmap_df["risk_debt"] / heatmap_df["total_outstanding"],
        0,
    )
    heatmap_pivot = heatmap_df.pivot(index="Service", columns="Directorate", values="risk_pct").fillna(0)
    fig_heat = px.imshow(
        heatmap_pivot,
        aspect="auto",
        text_auto=".0%",
        origin="lower",
    )
    fig_heat.update_layout(coloraxis_colorbar_title="Risk %")
    st.plotly_chart(fig_heat, use_container_width=True)

st.markdown("### Detail table")
view = (
    filtered.groupby(["Executive Directorate", "Directorate", "Service", "Sovservice"], as_index=False)
    .agg(
        balances=("Count of Total Balance Outstanding", "sum"),
        total_outstanding=("Sum of Total Balance Outstanding2", "sum"),
        risk_debt=("Risk Debt", "sum"),
        overdue_90=("Over 90 days", "sum"),
        overdue_180=("Over 180 days", "sum"),
        bucket_0_29=("Sum of 0-29 days", "sum"),
        bucket_30_59=("Sum of 30-59 days", "sum"),
        bucket_60_89=("Sum of 60-89 days", "sum"),
        bucket_90_180=("Sum of 90-180 days", "sum"),
        bucket_181_365=("Sum of 181 - 365 days", "sum"),
        bucket_365_plus=("Sum of >365 days", "sum"),
    )
    .sort_values("risk_debt", ascending=False)
)
view["risk_pct"] = np.where(view["total_outstanding"] != 0, view["risk_debt"] / view["total_outstanding"], 0)

st.dataframe(
    view,
    use_container_width=True,
    hide_index=True,
)

csv = view.to_csv(index=False).encode("utf-8")
st.download_button("Download filtered detail as CSV", data=csv, file_name="aged_debt_filtered_view.csv", mime="text/csv")

st.markdown("### Important note")
st.info(
    "This dataset appears to be a series of debt snapshots by date and service. It does not appear to contain an explicit collected / written-off status or a unique invoice/debtor key, so the dashboard focuses on ageing, risk, concentration and trend rather than confirmed recovery outcomes."
)

