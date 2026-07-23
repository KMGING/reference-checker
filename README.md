# IEEE Reference Checker Skill

这是一个用于 **检查和保守修复 IEEE Transactions 参考文献格式** 的本地 Skill。

参考文件是 IEEE Editorial Style Manual [https://journals.ieeeauthorcenter.ieee.org/your-role-in-article-production/ieee-editorial-style-manual/] 中的 IEEE Reference Guide

它适合在论文投稿前处理 `.bib`、以 BibTeX 为主要内容的 `.tex`、LaTeX `thebibliography` / `\bibitem`，也可以检查对话中粘贴的 BibTeX、bibitem 或纯文本参考文献。

默认策略是：**只检查、生成报告、不覆盖原始文件**。只有在用户明确要求“安全修复”或“生成修复副本”时，才会另存 `.ieee-fixed.*` 文件。

## 如何使用

通常不需要自己运行 Python 命令。你只要在 Codex 里用自然语言说明要检查哪个参考文献文件、是否只检查、是否生成修复副本即可。

首次使用前需要安装依赖。可以直接对 Codex 说：

```text
为 ieee-reference-checker 安装依赖。
```

对应的 Python 命令是：

```bash
cd ~/.codex/skills/ieee-reference-checker
python -m pip install -r requirements.txt
```

如果你只说“检查这个参考文献文件”，没有额外要求，默认行为是：**只生成 Markdown/JSON 检查报告，不修改原文件，也不生成修复副本**。

默认等价命令是：

```bash
python scripts/check_bibliography.py /path/to/ref.bib --check-only
```

最推荐的安全说法是：

```text
使用 ieee-reference-checker 检查 /path/to/ref.bib，只生成报告，不修改原文件。
```

如果你的参考文献写在 LaTeX 论文里，也可以这样说：

```text
使用 ieee-reference-checker 检查 /path/to/main.tex 里的参考文献，只检查，不修改源文件。
```

Codex 会自动识别输入是 `.bib`、BibTeX 风格的 `.tex`、`thebibliography` / `\bibitem`，还是粘贴的单条参考文献。



### 常用自然语言请求

只检查并生成报告：

```text
使用 ieee-reference-checker 检查 /path/to/ref.bib，只生成检查报告。
```

检查 LaTeX 文件里的内联 `bibitem`：

```text
使用 ieee-reference-checker 检查 /path/to/main.tex 的参考文献，不要修改原文件。
```

生成一个独立修复文件，但保留原文件：

```text
使用 ieee-reference-checker 检查并安全修复 /path/to/ref.bib，生成单独的 fixed 文件，不要覆盖原文件。
```

只检查某一个 citation key：

```text
使用 ieee-reference-checker 只检查 /path/to/ref.bib 里的 carlini2021extracting 这条参考文献。
```

只检查期刊、会议名称缩写：

```text
使用 ieee-reference-checker 只检查 /path/to/ref.bib 的 venue 格式。
```

只检查缺失字段：

```text
使用 ieee-reference-checker 检查 /path/to/ref.bib 里哪些条目缺少 DOI、页码、卷期等字段。
```

检查一条粘贴的 BibTeX：

```text
使用 ieee-reference-checker 检查下面这条 BibTeX，并告诉我哪些地方不符合 IEEE 格式：

@article{key,
  title={...}
}
```

需要联网核验 DOI 时，明确说出来：

```text
使用 ieee-reference-checker 检查 /path/to/ref.bib，并联网核验 DOI 是否存在。
```

默认不会联网。



### 推荐工作流

先检查：

```text
使用 ieee-reference-checker 检查 /path/to/ref.bib，只生成报告，不修改原文件。
```

确认报告后，再生成修复副本：

```text
使用 ieee-reference-checker 对 /path/to/ref.bib 应用安全修复，生成独立修复文件，不覆盖原文件。
```

最后验证修复副本：

```text
使用 ieee-reference-checker 验证 /path/to/ref.ieee-fixed.bib 是否还有可安全修复的问题。
```

## 输出结果

对 `ref.bib`，通常会生成：

- `ref.ieee-report.md`：给人阅读的问题报告。
- `ref.ieee-report.json`：结构化检查结果。
- `ref.ieee-fixed.bib`：修复后的独立文件，仅在请求生成修复副本时创建。

对 `.tex` 输入，报告仍会生成在同目录；如果请求修复副本，修复文件保持 `.tex` 后缀。

## 安全原则

默认行为是非破坏性的：

- 不覆盖原始 `.bib` 或 `.tex`。
- 不改 citation key。
- 不重排条目和字段。
- 不删除注释、自定义字段或重复条目。
- 不凭空生成 DOI、页码、卷号、期号、年份、会议届次、作者、出版社或文章编号。

如果你明确要求“直接修改原文件”，Codex 才会使用原地修改模式。该模式会先创建 `原文件.bak`，如果备份已存在则拒绝覆盖。

## 对应的 Python 命令

自然语言请求最终会映射到本地脚本。需要手动运行时，在 skill 目录执行：

```bash
cd ~/.codex/skills/ieee-reference-checker
```

安装依赖：

```bash
python -m pip install -r requirements.txt
```

只检查，不生成修复文件：

```bash
python scripts/check_bibliography.py ref.bib --check-only
```

生成独立修复文件：

```bash
python scripts/check_bibliography.py ref.bib --fix
```

验证修复结果：

```bash
python scripts/verify_fixed_bib.py ref.ieee-fixed.bib
```

只检查一个 citation key：

```bash
python scripts/check_bibliography.py ref.bib --key carlini2021extracting
```

只检查 venue：

```bash
python scripts/check_bibliography.py ref.bib --only venue
```

只检查缺失字段：

```bash
python scripts/check_bibliography.py ref.bib --only missing
```

检查单独条目：

```bash
python scripts/check_single_entry.py --stdin
```

显式原地修改：

```bash
python scripts/check_bibliography.py ref.bib --fix --in-place
```

## Skill 会自动修什么

`SAFE_FIX` 包括：

- 将 DOI resolver、`doi:` 前缀、空格和尾部标点规范化为纯 DOI。
- 将数字页码范围中的 `-` 改为 `--`，并删除 BibTeX `pages` 字段里的 `pp.`。
- 将 XLSX 精确匹配的 IEEE 期刊名替换为官方 `Reference Abbreviation`。
- 对已确认缩写或系统名添加局部大括号保护。
- 规范化已知字段名的小写形式。
- 应用 `venue_exceptions.yml` 中明确标为 `SAFE_FIX` 的会议形式。

## 哪些问题只提示人工确认

`SUGGESTED_FIX` 或 `MANUAL_REVIEW` 包括：

- 缺失 DOI、页码、卷期、月份、访问日期等元数据。
- 作者逗号结构、`et al.`、组织作者或不完整作者列表。
- USENIX Security 的届次或官方年份简称。
- CCS 等存在年份敏感正式名称的会议。
- 非 IEEE venue 中指南没有覆盖的词。
- 文章编号与页码字段选择。
- arXiv 与正式版本、重复条目的合并或删除。
- DOI、标题、年份或出版机构冲突。

Skill 永不凭空生成 DOI、页码、卷号、期号、年份、会议届次、作者、出版社或文章编号。

## IEEEabrv 项目处理

检查器会扫描输入文件同目录的 `.tex`，记录是否出现 `\bibliography{IEEEabrv,...}` 或相关配置，以及是否存在 `IEEEabrv.bib`。

由 XLSX 内部 acronym 可确定的 `IEEE_J_*` 宏会保留；无法解析的宏只报告，不强制展开。若同一数据库混用宏与字符串，会提示保持项目现有一致约定。

## 在线核验

默认完全关闭。需要时显式启用：

```bash
python scripts/check_bibliography.py ref.bib --verify-online
```

当前在线实现只使用 Crossref DOI API 验证 DOI 是否存在和标题相似度，并记录 provider 与请求 URL。它不会自动覆盖作者、页码、年份、卷期或 DOI。arXiv、出版社 proceedings、DBLP 等事实核验仍需人工或后续扩展；Google Scholar 不作为唯一来源。

## 本地规则来源

当前 Skill 随附：

- `references/IEEE_Reference_Style_Guide_for_Authors.docx`
- `references/List_of_IEEE_Journal_Magazine_Titles_Internal_Acronym_and_Reference_Abbreviation.xlsx`

原工作区提供的是 DOCX 指南，不是 PDF。构建器直接读取 DOCX 的文本与表格；也支持带可用文本层的 PDF。PDF 没有文本层时会明确失败，不会默认 OCR。原始来源文件不会被修改。

XLSX 使用 `openpyxl`，自动寻找 `Title` / `Full Title`、`Internal Acronym` / `Journal/Magazine`、`Reference Abbreviation` 等语义列，不依赖固定列号。指南 DOCX 使用 `python-docx` 识别会议常用词表和 `Common Abbreviations of Words in References` 表。每条期刊记录保留工作表和行号，每条单词规则保留章节、表格和行号。

## 重建规则库

替换 IEEE 指南或期刊缩写表后，可以重建本地规则库：

```bash
python scripts/build_rule_database.py \
  --guide references/IEEE_Reference_Style_Guide_for_Authors.docx \
  --journals references/List_of_IEEE_Journal_Magazine_Titles_Internal_Acronym_and_Reference_Abbreviation.xlsx
```

若替换成 PDF：

```bash
python scripts/build_rule_database.py \
  --guide references/IEEE_Reference_Style_Guide_for_Authors.pdf \
  --journals references/List_of_IEEE_Journal_Magazine_Titles_Internal_Acronym_and_Reference_Abbreviation.xlsx
```

输出文件：

- `data/ieee_journal_abbreviations.json`
- `data/ieee_word_abbreviations.json`
- `data/rule_sources.json`
- `data/unresolved_pdf_rules.txt`
- `data/unresolved_xlsx_rows.json`

当前本地数据生成 267 条可用 IEEE 期刊/杂志记录和 314 条通用/会议单词缩写。XLSX 中存在格式化产生的空行；数量指可用数据记录，不是工作表最大行号。

更新 IEEE 文件时建议：

1. 保留旧文件备份，但不要改写 IEEE 原文件。
2. 用新版本替换 `references/` 中对应 DOCX/PDF 或 XLSX。
3. 重新运行 `build_rule_database.py`。
4. 查看 `unresolved_pdf_rules.txt` 和 `unresolved_xlsx_rows.json`。
5. 用自己的 `.bib` 样例执行 `--fix`，再运行 `verify_fixed_bib.py` 验证修复结果。

## 已知限制

- 自带解析器面向常见 BibTeX；复杂 BibLaTeX 值拼接、跨字段宏表达式或严重损坏条目可能需要人工处理。
- 纯文本参考文献只能做保守模式诊断，不能可靠恢复所有字段。
- 非 IEEE venue 只使用本地指南中的词级规则；未覆盖的词不会猜测。
- DOCX 表格能可靠提取当前指南；不同版式 PDF 的表格文本可能进入 unresolved 文件，需要人工核对。
- 期刊工作簿包含历史 acronym/缩写；运行时以每行首个当前参考缩写作为主要值，并保留原始别名和来源行。
- 格式检查通过不等于作者、题目、年份、卷期、页码和 DOI 已与出版社元数据核验。

## License

MIT
