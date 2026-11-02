# 公开数据可获得性调研

> 目的：确认「不买守宫、只用公开数据」这条路能不能跑通。
> 调研日期：2026-11-02。检索方式：各平台官方 API 与搜索引擎站内检索。
> 操作规范见 `AGENTS.md`，路线影响见 `docs/roadmap.md`。

## 一、结论先行

**不存在「守宫蜕皮时序」类公开数据集，全世界都没有。**

这不是检索深度不够，是数据结构决定的：蜕皮是 3–6 周一次、每次持续 1–3 天的低频短时事件，公开平台只会沉淀「事件快照」（一张蜕皮中的照片），不会沉淀「同一只个体连续 30 天的每日影像」。而后者才是本项目核心算法（固定机位 + 每日对比 + 时序判断）需要的输入。

唯一真正对口的现成资产是 Roboflow Universe 上的 **`capstone-habql/gecko_1`**：1,163 张图像、Instance Segmentation、含 `gecko-shedding` 类别、**Public Domain** 许可。它解决的是「这一帧是不是蜕皮状态」，解决不了「还有几天蜕皮」——正好对应算法栈里可以外部预训练的第一层门控。

因此：**自采仍是唯一路径，但自采之前可以先把第一层门控训出来。**

## 二、搜过的平台与结果

| 平台 | 检索方式 | 结果 |
|---|---|---|
| HuggingFace Datasets | `search=gecko` / `leopard gecko` / `reptile` | 无蜕皮数据。`leopard gecko` 返回空数组；`reptile` 只有翻译语料与论坛文本 |
| GitHub | repositories `q=leopard+gecko` | 55 个仓库，全无关（EFM32 微控制器、销售聚类、MuJoCo 模拟） |
| GitHub | code search | 403，未认证限流，不可用 |
| Kaggle | `datasets/list?search=gecko` | 命中全是 CoinGecko 加密货币数据 |
| Kaggle | `datasets/list?search=shedding` | 病毒 shed、load shedding、vortex shedding，无爬宠 |
| iNaturalist | `taxon_name=Eublepharis macularius` | 3,250 条观察，多为 `captive: true`，CC-BY-NC、常见 2048×1536；**无蜕皮标注字段**，observation fields 为空 |
| LILA BC | 全站数据集列表 | 全是野生动物相机陷阱/无人机/热成像；有个体识别分类但不含爬宠 |
| Zenodo | `q=gecko shedding` | 论文预评审、壁虎趾垫生物力学数据、分类学图版，无蜕皮影像 |
| Figshare | `articles/search` | 端点只接受 POST，GET 返回 404，工具受限走不通 |
| Semantic Scholar | 关键词检索 | 429 Too Many Requests，无 key 不可用 |
| OpenAlex | `ecdysis image analysis` | 2,978 条，前 10 全是昆虫蜕皮分子机制（JH/ETH/CCAP 神经肽），无视觉识别 |
| OpenAlex | `reptile shedding computer vision` | 1,594 条，仅 3 条沾边（见第四节） |
| arXiv | API | 跨域重定向失败，未取得结果 |
| Reddit | `r/leopardgeckos/search.json` | 403，无 UA 被拦；改用搜索引擎可间接检索到帖 |
| Roboflow Universe | 搜索引擎站内检索 | **命中 `capstone-habql` 两个项目，见第三节** |
| 百度贴吧 | 站内检索页 / 搜索引擎 | 页面为 JS 空壳；经搜索引擎检索到经验帖，无结构化数据 |
| 哔哩哔哩 | 搜索 API | 412 request was banned；经搜索引擎检索到蜕皮记录视频 |
| YouTube | 搜索结果页 | JS 渲染，工具取不到内容 |
| leopardgecko.co.uk | 站内蜕皮页 | 8 张同一蜕皮周期的分阶段照片，见第五节 |

## 三、唯一对口资产：Roboflow `capstone-habql/gecko_1`

| 项目属性 | 值 |
|---|---|
| 工作区 / 项目 | `capstone-habql` / `gecko_1`（另有几乎同内容的 `gecko_2_2`） |
| 图像数 | 1,163 |
| 任务类型 | Instance Segmentation |
| 类别 | `gecko`、`gecko-abnormal`、`gecko-shedding` |
| 许可 | **Public Domain** |
| 版本 | `gecko_1` 有 1 个可导出数据集版本；`gecko_2_2` 版本数为 0 |
| 活跃度 | 3 年前更新，0 star，118 次浏览，4 次下载 |
| 项目说明 | 未填写描述 |

从样例文件名可以看出两个来源：一批 `shedding(40).jpg`、`shedding(79).jpg`、`shedding(179).jpg` 形态的编号序列，以及一批 Flickr 风格的 `11743099153_c87af72bda_o.jpg`。说明制作者是从公开图库按「蜕皮」关键词聚合的，不是自己养的守宫。

**下载受限**：`/dataset/1/download` 直接 GET 返回 403（Cloudflare 挑战页）。要导出需注册免费 Roboflow 账号取 API key，再走 `roboflow` Python 包导出。这是目前唯一需要人工介入的一步。

**它能做什么**：训练「画面里是否有蜕皮中的个体」「是否有异常皮肤」的二阶段门控。这正好是每日对比之前的第一道筛子——但它给不了时间维度。

## 四、次级可用资产

| 资产 | 规模与许可 | 与本项目的关系 |
|---|---|---|
| `jancquian/GeckoClassificationDataset`（GitHub） | 6 个分类学科各 420 张，共 2,520 张原图 + 2,520 张裁剪图 | 物种/形态分类，可做骨干网络预训练；无蜕皮标签 |
| iNaturalist 豹纹守宫观察 | 3,250 条，CC-BY-NC | 真实家庭饲养环境下的守宫照片，可做域内负样本与背景噪声；**NC 限制不可商用** |
| `MZVGroup/geckodaily-knowledge`（HuggingFace） | cc-by-4.0，1K–10K 条，3,500+ 护理指南 | 结构化护理知识（ feeders、feeding schedules、supplements、substrates、health conditions、morphs），供知识库 RAG 用，不是图像数据 |
| `vencerlanz09/reptiles-and-amphibians-image-dataset`（Kaggle） | 141 MB，2,455 次下载，许可 "Other" | 物种分类，无蜕皮标签 |
| `mlnomad/imnet1k_banded_gecko`（HuggingFace） | 1K–10K，parquet | 带纹壁虎，非豹纹守宫，参考价值有限 |

学术侧唯一可借鉴的三条：`BioCLIP`（2024，生物界视觉基础模型，可做骨干）、`Anolis carolinensis` 变色研究（2025，用 iNaturalist 数据 + 计算机视觉做生理性状分析，方法论同构）、`ReptiLearn`（2024，家庭饲养箱自动化行为实验系统，硬件思路可参考）。**没有任何一篇论文做过爬行动物蜕皮的视觉识别。**

## 五、两个小样本但结构正确的线索

**leopardgecko.co.uk 的蜕皮页**（`/documents/caresheet/shedding.htm`）：`gfx/shed/s1.jpg`–`s8.jpg`，同一只豹纹守宫在一个蜕皮周期内的 8 个阶段，摄影师 Deborah Rayment 授权。这是全网找到的唯一「同个体、同周期、分阶段」的真实照片序列，与我们的算法假设完全同构——但只有 8 张，且站点无明确再许可条款，只能作为人工判读参考，不能入训练集。

**哔哩哔哩 `BV1F27RzHEfB`**「健康守宫丝滑蜕皮记录」：完整蜕皮过程视频。同类视频在 B 站与 YouTube 上不缺，但都是「蜕皮发生的那几十分钟」，没有「蜕皮前两周」的连续素材——这正好是我们要预测的那段，恰恰没人拍。

## 六、对路线图的影响

1. `docs/roadmap.md` 里「数据是关键路径」的判断被这次调研证实，且理由更硬：不是「没找到」，是「公开平台的结构不产生这类数据」。
2. 原计划「Phase 2 用手机临时机位启动采集」不变，仍是唯一出路。等待公开数据的路可以正式关闭。
3. 新增一项可并行的低成本动作：注册 Roboflow 账号导出 `gecko_1`，用于第一层门控的预训练与验证。这是纯增量，不影响自采主线。
4. iNaturalist 数据受 CC-BY-NC 限制，只能用于内部验证，不能进入任何对外交付物。若将来要商用模型，需替换为自采数据。