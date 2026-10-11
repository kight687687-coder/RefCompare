# RefCompare 中文快速说明

RefCompare 是一个 Python 命令行工具，用于比较 OpenAlex 与 Crossref 收录的 DOI 参考文献，并检验参考文献差异对受控的一跳引文网络局部排名的影响。首版面向用户提供的小批量 DOI（通常几十篇）。

## 安装

需要 Python 3.10 或更高版本：

```powershell
git clone --branch v0.1.1 https://github.com/kight687687-coder/RefCompare.git
cd RefCompare
python -m pip install .
refcompare --help
```

如果系统没有把 Python Scripts 目录加入 `PATH`，可用 `python -m refcompare --help` 和 `python -m refcompare run ...`。

开发和运行测试时：

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

## 在线运行

建立一个 UTF-8 文本文件，每行写一个种子论文 DOI；可以写 DOI 本身，也可以写 DOI 链接。空行和以 `#` 开头的注释行会跳过。

在 PowerShell 中设置你自己的 Crossref 联系邮箱并运行：

```powershell
$env:CROSSREF_MAILTO = "you@example.org"
refcompare run --dois seed_dois.txt --output results/my_run
```

也可以使用 `--mailto` 参数。OpenAlex API 密钥可选，通过 `OPENALEX_API_KEY` 环境变量或 `--openalex-api-key` 参数设置。邮箱和密钥只用于请求，不会写入运行清单或日志。

运行完成后先打开 `results/my_run/summary.md` 查看通俗解释。目录内还会保存完整数据快照和逐篇 CSV。

## 离线复算

保存的数据包包含离线重算所需的 OpenAlex、Crossref 和 citing-work 快照：

```powershell
refcompare analyze --input-dir results/my_run
```

默认结果写入 `results/my_run/reanalyzed`；可以用 `--output` 指定其他目录。这一步不会请求 API。

## 怎么理解主要结果

默认按论文口径：仅用 **clean-comparable seeds** 建图，即两个来源请求成功、OpenAlex 提供参考文献字段、两来源有效 DOI 参考文献集合均非空。全部提交记录仍保留在参考文献指标和质量分组表中。ASP 在包含 seed、reference 和 citing 节点的完整一跳网络上计算；随后只比较每对图 **共同的被引文献**，资格由两图各自 reference 边目标确定。某 DOI 同时充当 seed/citing 时，只有在两图也具有被引文献角色才进入排名。没有可比对象时输出空排名，不自动扩大范围。

- **Jaccard 相似度**：两来源共同 DOI 参考文献数除以两来源观察到的 DOI 集合并集。越高表示观察到的集合重合越多。
- **参考文献覆盖比（RCR）**：某来源的 DOI 参考文献数除以相同的观察并集。它是现有可识别数据的诊断指标，并不代表完整参考文献召回率。
- **ASP**：在每个构造的一跳网络内部计算的局部 prestige-style 分数，不是学术声望的绝对值。
- **Kendall tau-b / Spearman rho**：默认比较两张网络共同被引文献的排序一致性。
- **Top-k 重合和排名位移**：说明高排名作品有多少重合，以及共同作品平均移动了多少名次。

报告结论只适用于本次提交的种子论文和抓取到的 API 快照。没有 DOI 或无法解析 DOI 的参考文献可能无法匹配；API 数据会随时间变化；排名分析限于受控的一跳网络。结果不能据此推断某个数据库总体上更优。

## 参数和输出

默认范围为 `--graph-scope clean-comparable` 和 `--ranking-scope common-references`，ASP damping `0.85`、收敛容差 `1e-8`、最多 `100` 次迭代、Top fraction `0.10`。高级用户可以通过命令行覆盖，实际范围和参数会记录在运行清单及 CSV 中。

如需显式使用 0.1.0 的较宽分析范围：

```powershell
refcompare analyze --input-dir results/my_run --graph-scope all-records --ranking-scope all-common-nodes
```

`run` 和 `analyze` 均支持这两个参数，也可以独立选择。离线复算继承已保存范围，命令行覆盖优先；没有范围字段的旧数据包采用论文默认值。复算输出保留快照，支持再次复算。较宽范围是额外诊断，与论文主分析不同。

主要输出包括：运行清单 `run_manifest.json`、原始数据快照 `raw/`、参考文献指标 `reference_metrics.csv`、分组汇总 `reference_groups.csv`、网络统计 `graph_statistics.csv`、ASP 分数 `asp_scores.csv`、排名汇总和明细 CSV，以及通俗结果报告 `summary.md`。

`analysis_scope.csv` 记录实际建图和排名范围，以及提交记录数、clean-comparable 数和网络 seed 数。排名汇总同时记录每图具有比较资格的文献数和每对图共同对象数。

抓取到的 reference/citing DOI 使用论文的操作性规范化规则：转小写，移除 DOI URL/`doi:` 前缀和尾部标点，要求以 `10.` 开头且包含 `/`。这会保留原始快照中的部分格式异常字符串，不验证 DOI 注册真实性；用户输入的 seed DOI 仍采用较严格的格式校验。同输入结果一致性依赖这一规则。

0.1.1 为与论文方法对齐的版本，固定代码与研究数据见 [v0.1.1 发布页](https://github.com/kight687687-coder/RefCompare/releases/tag/v0.1.1)。固定 Top-k 采用分数降序、DOI 升序；并列扩展集合保留全部达到截断分数的对象，另报集合大小及 Jaccard。历史导出文件部分截断采用旧的行顺序，因此保留历史文件，并按论文规则从原始分数独立重建基准。原始研究工作区的验证命令仍为 `python scripts/verify_paper_parity.py --study-root 研究工作区路径 --output 验证输出路径`。

## 固定研究数据与复现包

下载 [RefCompare_research_data_20261011.zip](https://github.com/kight687687-coder/RefCompare/releases/download/v0.1.1/RefCompare_research_data_20261011.zip)，解压后按 README 运行。包内包含 10,000 个样本的精简 DOI 数据快照、主分析和配对 2×3 分析的输入与结果、检索状态、图示源数据、固定软件及依赖版本、SHA-256 校验清单。已验证的环境为 Python 3.14。

```powershell
python -m pip install -r requirements.txt
python reproduce_primary.py
python robustness_final.py
python verify_reproduction.py --output reproduction_validation
```

安装依赖后，两个分析均离线运行。主分析使用每对图共同的参考文献目标；研究专用 2×3 驱动使用每学科六个变体共同的 shared-edge 目标集合。精简快照保留 DOI 复算所需字段，不包含所有原始书目字段。历史导出结果与论文规则复算结果分开存放，附截断差异说明。

## 引用与许可证

请引用 RefCompare GitHub 仓库和配套论文。软件采用 MIT 许可证，详见 [LICENSE](LICENSE)。
