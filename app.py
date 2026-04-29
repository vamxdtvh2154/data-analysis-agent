import os
import io
import json
import sqlite3
import datetime as dt
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from dotenv import load_dotenv

try:
from openai import OpenAI
except Exception:
OpenAI = None


APP_TITLE = "AI 数据分析 + 自动报告 Agent"
DB_PATH = "analysis_history.db"


load_dotenv()


def get_env(name: str, default: str = "") -> str:
value = os.getenv(name)
return value if value is not None and value != "" else default


OPENAI_API_KEY = get_env("OPENAI_API_KEY")
OPENAI_MODEL = get_env("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = get_env("OPENAI_BASE_URL")


def init_db() -> None:
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute(
"""
CREATE TABLE IF NOT EXISTS reports (
id INTEGER PRIMARY KEY AUTOINCREMENT,
created_at TEXT NOT NULL,
file_name TEXT,
mode TEXT,
question TEXT,
report TEXT NOT NULL
)
"""
)
conn.commit()
conn.close()


def save_report(file_name: str, mode: str, question: str, report: str) -> None:
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute(
"INSERT INTO reports (created_at, file_name, mode, question, report) VALUES (?, ?, ?, ?, ?)",
(dt.datetime.now().isoformat(timespec="seconds"), file_name, mode, question, report),
)
conn.commit()
conn.close()


def load_reports(limit: int = 10) -> pd.DataFrame:
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query(
"SELECT created_at, file_name, mode, question, report FROM reports ORDER BY id DESC LIMIT ?",
conn,
params=(limit,),
)
conn.close()
return df


def read_uploaded_file(uploaded_file) -> pd.DataFrame:
name = uploaded_file.name.lower()

if name.endswith(".csv"):
data = uploaded_file.getvalue()
for enc in ["utf-8-sig", "utf-8", "gbk", "gb18030"]:
try:
return pd.read_csv(io.BytesIO(data), encoding=enc)
except Exception:
continue
return pd.read_csv(io.BytesIO(data))

if name.endswith(".xlsx") or name.endswith(".xls"):
return pd.read_excel(uploaded_file)

raise ValueError("只支持 CSV / Excel 文件。")


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
result = df.copy()
result.columns = [str(c).strip().replace("\n", " ") for c in result.columns]
return result


def infer_column_types(df: pd.DataFrame) -> pd.DataFrame:
rows = []
for col in df.columns:
s = df[col]
dtype = str(s.dtype)
non_null = int(s.notna().sum())
missing = int(s.isna().sum())
unique = int(s.nunique(dropna=True))
sample_values = s.dropna().astype(str).head(5).tolist()

if pd.api.types.is_numeric_dtype(s):
role = "numeric"
elif pd.api.types.is_datetime64_any_dtype(s):
role = "datetime"
else:
parsed = pd.to_datetime(s, errors="coerce")
if parsed.notna().mean() > 0.75 and non_null > 0:
role = "datetime-like"
elif unique <= max(20, len(df) * 0.05):
role = "categorical"
else:
role = "text"

rows.append(
{
"column": col,
"inferred_role": role,
"dtype": dtype,
"non_null": non_null,
"missing": missing,
"unique": unique,
"sample_values": ", ".join(sample_values),
}
)
return pd.DataFrame(rows)


def dataframe_profile(df: pd.DataFrame) -> Dict[str, Any]:
numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
object_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()

missing = df.isna().sum().sort_values(ascending=False)
missing = missing[missing > 0]

duplicate_rows = int(df.duplicated().sum())

numeric_summary = {}
if numeric_cols:
numeric_summary = df[numeric_cols].describe().round(4).to_dict()

categorical_summary = {}
for col in object_cols[:12]:
vc = df[col].astype(str).value_counts(dropna=True).head(8)
categorical_summary[col] = vc.to_dict()

return {
"rows": int(df.shape[0]),
"columns": int(df.shape[1]),
"column_names": df.columns.tolist(),
"numeric_columns": numeric_cols,
"non_numeric_columns": object_cols,
"missing_values": missing.to_dict(),
"duplicate_rows": duplicate_rows,
"numeric_summary": numeric_summary,
"categorical_summary": categorical_summary,
}


def to_markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
if df.empty:
return ""
return df.head(max_rows).to_markdown(index=False)


def compact_context(df: pd.DataFrame, file_name: str) -> str:
profile = dataframe_profile(df)
types_df = infer_column_types(df)

sample = df.head(20).copy()
for col in sample.columns:
sample[col] = sample[col].astype(str).str.slice(0, 80)

parts = []
parts.append(f"文件名: {file_name}")
parts.append(f"数据规模: {profile['rows']} 行, {profile['columns']} 列")
parts.append("字段列表: " + ", ".join(profile["column_names"]))
parts.append("\n字段类型识别:\n" + to_markdown_table(types_df, 80))
parts.append("\n缺失值:\n" + json.dumps(profile["missing_values"], ensure_ascii=False, indent=2))
parts.append("\n重复行数量: " + str(profile["duplicate_rows"]))
parts.append("\n数值字段统计:\n" + json.dumps(profile["numeric_summary"], ensure_ascii=False, indent=2)[:7000])
parts.append("\n分类字段 Top 值:\n" + json.dumps(profile["categorical_summary"], ensure_ascii=False, indent=2)[:7000])
parts.append("\n前 20 行样例:\n" + sample.to_csv(index=False))

return "\n".join(parts)


def run_openai(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> Optional[str]:
if not OPENAI_API_KEY or OpenAI is None:
return None

try:
if OPENAI_BASE_URL:
client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
else:
client = OpenAI(api_key=OPENAI_API_KEY)

response = client.responses.create(
model=OPENAI_MODEL,
input=[
{"role": "system", "content": system_prompt},
{"role": "user", "content": user_prompt},
],
temperature=temperature,
)
return response.output_text

except Exception as e:
return f"OPENAI_ERROR: {e}"


def local_basic_report(df: pd.DataFrame, file_name: str, question: str) -> str:
profile = dataframe_profile(df)
types_df = infer_column_types(df)

lines = []
lines.append(f"# {APP_TITLE} - 本地基础报告")
lines.append("")
lines.append("## 1. 数据概览")
lines.append(f"- 文件名：{file_name}")
lines.append(f"- 行数：{profile['rows']}")
lines.append(f"- 列数：{profile['columns']}")
lines.append(f"- 重复行：{profile['duplicate_rows']}")
lines.append("")
lines.append("## 2. 字段识别")
lines.append(types_df.to_markdown(index=False))
lines.append("")
lines.append("## 3. 缺失值")
if profile["missing_values"]:
for k, v in profile["missing_values"].items():
lines.append(f"- {k}: {v}")
else:
lines.append("- 未发现明显缺失值。")
lines.append("")
lines.append("## 4. 数值字段基础统计")
numeric_cols = profile["numeric_columns"]
if numeric_cols:
lines.append(df[numeric_cols].describe().round(4).to_markdown())
else:
lines.append("- 没有识别到数值字段。")
lines.append("")
lines.append("## 5. 针对问题的初步结论")
lines.append(f"用户问题：{question or '未填写具体问题'}")
lines.append("")
lines.append("当前没有配置 OPENAI_API_KEY，因此只生成本地统计报告。配置 API Key 后，会启用自然语言分析、多 Agent 协作、异常归因和自动报告生成。")
return "\n".join(lines)


def build_agent_prompts(context: str, question: str) -> Dict[str, str]:
q = question.strip() or "请基于这份数据生成一份完整的业务分析报告。"

return {
"cleaning": f"""
你是数据清洗 Agent。请阅读下面的数据画像，判断数据质量问题。
重点输出：
1. 字段含义推测
2. 缺失值和重复值风险
3. 异常值或口径不一致风险
4. 分析前需要注意的事项
5. 建议的数据清洗步骤

用户问题：
{q}

数据上下文：
{context}
""",
"analysis": f"""
你是指标分析 Agent。请基于数据上下文和用户问题提出分析结论。
重点输出：
1. 应该关注的核心指标
2. 趋势变化
3. 分组差异
4. 异常点
5. 可能原因
6. 需要进一步验证的数据

用户问题：
{q}

数据上下文：
{context}
""",
"business": f"""
你是业务解释 Agent。请把数据分析转化为业务人员能理解的结论。
重点输出：
1. 发生了什么
2. 为什么可能发生
3. 对业务有什么影响
4. 可以马上做什么
5. 风险和机会

用户问题：
{q}

数据上下文：
{context}
""",
"report": f"""
你是报告生成 Agent。请基于前面各 Agent 的结论，生成一份结构化中文报告。
报告必须包含：
1. 管理层摘要
2. 数据概览
3. 关键发现
4. 异常与风险
5. 业务解释
6. 行动建议
7. 后续跟进清单

用户问题：
{q}
""",
"review": f"""
你是质量复核 Agent。请审查报告是否存在：
1. 结论过度推断
2. 缺少数据依据
3. 表达不清
4. 建议不可执行
5. 需要补充验证的地方

请输出改进后的最终报告。
""",
}


def generate_report(df: pd.DataFrame, file_name: str, question: str, mode: str) -> str:
context = compact_context(df, file_name)
prompts = build_agent_prompts(context, question)

system = "你是一个严谨的数据分析 Agent。必须区分数据事实、合理推测和需要进一步验证的内容。回答用中文，结构清晰，不要编造数据。"

if not OPENAI_API_KEY:
return local_basic_report(df, file_name, question)

if mode == "Quick":
prompt = f"""
请基于下面的数据上下文回答用户问题，并生成简洁报告。

用户问题：
{question or "请生成一份简洁的数据分析报告。"}

数据上下文：
{context}
"""
result = run_openai(system, prompt)
return result or local_basic_report(df, file_name, question)

cleaning = run_openai(system, prompts["cleaning"]) or ""
analysis = run_openai(system, prompts["analysis"]) or ""
business = run_openai(system, prompts["business"]) or ""

report_prompt = f"""
请综合以下多 Agent 输出，生成一份完整中文业务分析报告。

【数据清洗 Agent 输出】
{cleaning}

【指标分析 Agent 输出】
{analysis}

【业务解释 Agent 输出】
{business}

用户原始问题：
{question or "请生成完整业务分析报告。"}

要求：
- 不要编造原始数据中没有的事实
- 明确区分事实、推测、建议
- 输出行动清单
- 适合发给老板或业务负责人阅读
"""
report = run_openai(system, report_prompt) or ""

if mode == "Deep":
review_prompt = f"""
下面是一份 AI 数据分析报告。请你作为质量复核 Agent 进行二次审查和重写。

原报告：
{report}

请输出最终增强版报告，要求：
1. 结论更清晰
2. 风险提示更明确
3. 行动建议更可执行
4. 标出哪些结论需要更多数据验证
5. 适合直接作为 Markdown 报告保存
"""
reviewed = run_openai(system, review_prompt) or report
return reviewed

return report


def make_download_button(text: str, file_name: str, content: str) -> None:
st.download_button(
label=text,
data=content.encode("utf-8"),
file_name=file_name,
mime="text/markdown",
)


def render_chart_area(df: pd.DataFrame) -> None:
st.subheader("可视化图表")

numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
if not numeric_cols:
st.info("没有数值字段，无法生成数值图表。")
return

chart_type = st.selectbox("图表类型", ["数值字段分布", "两个数值字段散点图", "分类字段分组求和"])
if chart_type == "数值字段分布":
col = st.selectbox("选择数值字段", numeric_cols)
fig, ax = plt.subplots()
df[col].dropna().plot(kind="hist", bins=30, ax=ax)
ax.set_title(f"{col} distribution")
ax.set_xlabel(col)
st.pyplot(fig)

elif chart_type == "两个数值字段散点图":
x = st.selectbox("X 轴", numeric_cols, index=0)
y = st.selectbox("Y 轴", numeric_cols, index=min(1, len(numeric_cols) - 1))
fig, ax = plt.subplots()
ax.scatter(df[x], df[y])
ax.set_xlabel(x)
ax.set_ylabel(y)
ax.set_title(f"{x} vs {y}")
st.pyplot(fig)

else:
cat_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
if not cat_cols:
st.info("没有分类字段。")
return
cat = st.selectbox("分类字段", cat_cols)
val = st.selectbox("求和字段", numeric_cols)
grouped = df.groupby(cat, dropna=False)[val].sum().sort_values(ascending=False).head(20)
fig, ax = plt.subplots()
grouped.plot(kind="bar", ax=ax)
ax.set_title(f"{val} by {cat}")
ax.set_xlabel(cat)
ax.set_ylabel(val)
st.pyplot(fig)


def render_sidebar() -> Tuple[str, bool]:
st.sidebar.title("设置")
mode = st.sidebar.radio(
"分析模式",
["Quick", "Standard", "Deep"],
index=1,
help="Quick 单次调用；Standard 多 Agent 协作；Deep 多 Agent + 复核，token 使用量更高。",
)
show_history = st.sidebar.checkbox("显示历史报告", value=True)
st.sidebar.markdown("---")
st.sidebar.write("当前模型：", OPENAI_MODEL)
if OPENAI_API_KEY:
st.sidebar.success("已检测到 OPENAI_API_KEY")
else:
st.sidebar.warning("未检测到 OPENAI_API_KEY，将使用本地基础报告模式。")
return mode, show_history


def main() -> None:
st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")
init_db()

mode, show_history = render_sidebar()

st.title(APP_TITLE)
st.write("上传 Excel / CSV，用自然语言提出问题，系统会进行字段识别、数据画像、异常检查、多 Agent 分析和自动报告生成。")

uploaded = st.file_uploader("上传数据文件", type=["csv", "xlsx", "xls"])

if uploaded is None:
st.info("可以先使用项目里的 sample_data/sales_sample.csv 进行测试。")
if show_history:
st.subheader("历史报告")
hist = load_reports()
if not hist.empty:
st.dataframe(hist[["created_at", "file_name", "mode", "question"]], use_container_width=True)
else:
st.caption("暂无历史报告。")
return

try:
df = read_uploaded_file(uploaded)
df = clean_column_names(df)
except Exception as e:
st.error(f"读取文件失败：{e}")
return

st.subheader("数据预览")
st.dataframe(df.head(100), use_container_width=True)

profile = dataframe_profile(df)
types_df = infer_column_types(df)

c1, c2, c3, c4 = st.columns(4)
c1.metric("行数", profile["rows"])
c2.metric("列数", profile["columns"])
c3.metric("数值字段", len(profile["numeric_columns"]))
c4.metric("重复行", profile["duplicate_rows"])

with st.expander("字段类型识别", expanded=True):
st.dataframe(types_df, use_container_width=True)

with st.expander("缺失值与基础统计", expanded=False):
st.write("缺失值：")
st.json(profile["missing_values"])
if profile["numeric_columns"]:
st.write("数值字段统计：")
st.dataframe(df[profile["numeric_columns"]].describe().round(4), use_container_width=True)

render_chart_area(df)

st.subheader("自然语言分析")
question = st.text_area(
"你想让 Agent 分析什么？",
value="请分析这份数据的主要趋势、异常点、可能原因，并生成一份给老板看的业务报告。",
height=100,
)

estimated_context_chars = len(compact_context(df, uploaded.name))
st.caption(f"当前压缩上下文约 {estimated_context_chars:,} 字符。Deep 模式会触发更多 Agent 调用，适合压测长上下文和多轮推理。")

if st.button("生成分析报告", type="primary"):
with st.spinner("正在生成报告..."):
report = generate_report(df, uploaded.name, question, mode)
save_report(uploaded.name, mode, question, report)

st.subheader("分析报告")
st.markdown(report)
make_download_button("下载 Markdown 报告", "analysis_report.md", report)

if show_history:
st.subheader("历史报告")
hist = load_reports()
if not hist.empty:
st.dataframe(hist[["created_at", "file_name", "mode", "question"]], use_container_width=True)
with st.expander("查看最近一份报告全文"):
st.markdown(hist.iloc[0]["report"])
else:
st.caption("暂无历史报告。")


if __name__ == "__main__":
main()
