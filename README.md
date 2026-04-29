# AI 数据分析 + 自动报告 Agent

这是一个面向中小企业和个人的 AI 数据分析 Agent 原型。

项目目标：让不会写代码的人，也能通过自然语言分析 Excel / CSV 数据，并自动生成业务报告、趋势结论、异常解释和行动建议。

## 核心痛点

很多业务人员手里有销售、客户、订单、库存、投放等数据，但缺少数据分析能力：

- 不知道哪些指标重要
- 不会从 Excel 中发现趋势和异常
- 不会把数据结论写成老板能看的报告
- 不会把分析结果转化成可执行动作
- 缺少持续复盘和历史报告沉淀

本项目希望把这些流程自动化。

## 核心功能

- 上传 CSV / Excel 文件
- 自动识别字段类型
- 自动生成数据画像
- 检查缺失值、重复值、异常风险
- 生成基础统计分析
- 支持自然语言提问
- 支持 Quick / Standard / Deep 三种分析模式
- 支持多 Agent 协作式分析
- 自动生成 Markdown 报告
- 本地 SQLite 保存历史报告
- 没有 API Key 时也能生成本地基础报告

## 三种分析模式

### Quick

单次模型调用，适合快速问答和轻量分析。

### Standard

多 Agent 协作：

- 数据清洗 Agent
- 指标分析 Agent
- 业务解释 Agent
- 报告生成 Agent

### Deep

在 Standard 基础上增加质量复核 Agent，用于更长报告、更复杂分析和更高 token 压测。

## 核心逻辑流

文件上传
→ 字段识别
→ 数据清洗检查
→ 指标计算
→ 趋势分析
→ 异常归因
→ 多 Agent 协作
→ 报告生成
→ 质量复核
→ 历史报告保存

## Token 使用说明

这个项目属于较高 token 使用场景。

一次完整的数据分析任务通常包括：

- 文件结构理解
- 字段识别
- 数据清洗解释
- 指标计算方案
- 趋势分析
- 异常归因
- 业务建议生成
- 报告撰写
- 多轮修改
- 多 Agent 复核

常规测试阶段，预计每日运行 20 到 50 次任务，日消耗约 100 万到 300 万 tokens。

在压测阶段，如果进行批量表格分析、多文件对比、报告反复修订和多 Agent 交叉验证，预计每日运行 40 到 100 次复杂任务，峰值 token 消耗可能达到 500 万到 1000 万 tokens。

随着项目继续开发，后续计划增加：

- 多文件批量分析
- 跨月份经营数据对比
- 自动图表解释
- 历史分析记录检索
- 报告版本迭代
- 数据问答记忆
- 多 Agent 复核
- 自动生成经营建议

这些功能会增加长上下文处理、多轮推理和多次模型调用需求，因此 token 消耗会继续上升。

## 安装方法

1. 安装依赖

pip install -r requirements.txt

2. 复制环境变量文件

Windows:

copy .env.example .env

macOS / Linux:

cp .env.example .env

3. 打开 .env，填写 API Key

OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini

4. 启动项目

streamlit run app.py

## 文件结构

data_analysis_agent/
- app.py
- requirements.txt
- README.md
- .env.example
- .gitignore
- sample_data/
- sales_sample.csv


