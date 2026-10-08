# RefCompare 中文快速说明

RefCompare 是一个 Python 命令行工具，用于比较 OpenAlex 与 Crossref 收录的 DOI 参考文献，并检验参考文献差异对受控的一跳引文网络局部排名的影响。首版面向用户提供的小批量 DOI（通常几十篇）。

## 安装

需要 Python 3.10 或更高版本：

```powershell
git clone https://github.com/kight687687-coder/RefCompare.git
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

- **Jaccard 相似度**：两来源共同 DOI 参考文献数除以两来源观察到的 DOI 集合并集。越高表示观察到的集合重合越多。
- **参考文献覆盖比（RCR）**：某来源的 DOI 参考文献数除以相同的观察并集。它是现有可识别数据的诊断指标，并不代表完整参考文献召回率。
- **ASP**：在每个构造的一跳网络内部计算的局部 prestige-style 分数，不是学术声望的绝对值。
- **Kendall tau-b / Spearman rho**：比较两张网络中共同作品的排序一致性。
- **Top-k 重合和排名位移**：说明高排名作品有多少重合，以及共同作品平均移动了多少名次。

报告结论只适用于本次提交的种子论文和抓取到的 API 快照。没有 DOI 或无法解析 DOI 的参考文献可能无法匹配；API 数据会随时间变化；排名分析限于受控的一跳网络。结果不能据此推断某个数据库总体上更优。

## 参数和输出

默认值遵循论文方法：ASP damping `0.85`、收敛容差 `1e-8`、最多 `100` 次迭代、Top fraction `0.10`。高级用户可以通过命令行覆盖，参数会记录在运行清单中。

主要输出包括：运行清单 `run_manifest.json`、原始数据快照 `raw/`、参考文献指标 `reference_metrics.csv`、分组汇总 `reference_groups.csv`、网络统计 `graph_statistics.csv`、ASP 分数 `asp_scores.csv`、排名汇总和明细 CSV，以及通俗结果报告 `summary.md`。

## 引用与许可证

请引用 RefCompare GitHub 仓库和配套论文。软件采用 MIT 许可证，详见 [LICENSE](LICENSE)。
