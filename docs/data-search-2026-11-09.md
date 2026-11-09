# 全网蜕皮数据搜索记录（2026-11-09）

## 目的

在启动 Phase 2 自采之前，穷尽互联网上可能存在的守宫蜕皮相关数据，重点寻找：
1. 蒙白（pre-shed / opaque）标注图片
2. 红外 / 夜视守宫照片
3. 同一守宫的跨天时序影像
4. 任何可直接使用的蜕皮状态分类数据集

## 搜索范围与结果

| 平台 | 可达性 | 结果 |
|------|--------|------|
| Kaggle API | ✅ | 无蜕皮数据集；「Reptiles and Amphibians Image Dataset」仅按物种分类，无蜕皮状态标注 |
| GitHub API | ✅ | 搜索 gecko/reptile/ecdysis/shedding 相关仓库，零个有用结果 |
| iNaturalist API | ✅ | Gekkota + "shedding" 文字搜索仅 10 条，Eublepharis macularius 仅 9 条；大部分拍的是蜕下的皮而非守宫本体 |
| 搜狗（网页+图片） | ✅ | 主要收获来源；中英文关键词 24 组，搜到 682 个图片 URL |
| Bilibili API | ✅（搜索接口需 WBI 签名，绕行用搜狗间接发现） | 主要收获来源；从搜狗图片结果提取到 39+23 个 BV 号，筛出 25 个蜕皮相关视频 |
| Roboflow Universe | ❌ 403 Cloudflare | 现有 gecko1 数据的来源平台，无法再搜索 |
| HuggingFace | ❌ 超时 | 国内网络不可达 |
| YouTube | ❌ 超时 | 国内网络不可达 |
| Zenodo | ❌ 403 | 被限流 |
| Papers With Code | ❌ 超时 | 不可达 |

**核心结论：互联网上不存在标注好的守宫蜕皮状态数据集。**

## 收集到的数据

保存于 `data/collected/`（gitignore，仅本地）：

| 来源 | 数量 | 说明 |
|------|------|------|
| `data/collected/bilibili/` | 129 张 | 17 个 B 站守宫蜕皮视频，每 10 秒抽 1 帧，检测器过滤后保留检出守宫的帧 |
| `data/collected/sogou/` | 259 张 | 搜狗图片搜索 24 组关键词，下载后经检测器过滤 |
| `data/collected/inat/` | 29 张 | iNaturalist "shedding"/"shed skin" 关键词命中的守宫照片 |
| **合计** | **417 张** | |

### 自动分类统计（现有二态模型，仅供参考）

| 分类 | 视频帧 | 搜狗图片 | iNaturalist |
|------|------|------|------|
| shedding | 140 | 190 | 20 |
| normal | 56 | 69 | 9 |
| 未检出 | 50 | 23 | 4 |

> 以上由 gecko-state.onnx 自动标注，未经人工复核。搜狗图片来源混杂（B 站封面、搜狐文章、知乎、商品图），可能包含非守宫图片。

### 数据特征

- **视频帧**（最高价值）：真实饲养箱环境（纸巾底、塑料盒、玻璃缸），中国饲养者拍摄，覆盖蜕皮全过程（含卡皮处理）。缺点：有 B 站水印、分辨率 360p–480p、全是可见光。
- **搜狗图片**（中等价值）：来源混杂，分辨率跨度大（280×158 到 1728×1080），部分图片是「雪花基因」等天然浅色守宫（不是蒙白，但视觉上易混淆）。
- **iNaturalist**（低价值）：野外照片，大部分是蜕下的空皮。

## 未找到的数据（关键缺口）

1. **蒙白（pre-shed）标注图片**：零。蒙白期只有 1–2 天，几乎没有饲主专门拍这个状态发到网上。搜狗搜「蒙白」的结果里可能有一两张真实蒙白照片（需人工确认），但量级远远不够训练。
2. **红外 / 夜视照片**：零。所有收集到的图片都是可见光。
3. **同一守宫跨天时序**：零。视频覆盖的是单次蜕皮过程（几小时），不是跨天序列。

## 下一步建议

1. **人工复核** `data/collected/` 的 417 张图，剔除误检与不相关图片，按 normal / shedding / 疑似蒙白 三类手动标注。
2. **扩充训练集**：复核后的图片加入 `ml/datasets/gecko-state/`，重新训练分类器。
3. **启动 Phase 2 自采**：蒙白和时序数据只有自己拍才拿得到。这是唯一路径。

## 搜索脚本

临时脚本保存在 `.tmp/`（gitignore）：
- `search1–10.py`：各平台探测与搜索
- `dl_videos.py` / `dl_rest.py` / `dl_new.py`：B 站视频下载
- `extract_frames.py` / `extract_all.py`：视频抽帧
- `dl_sogou.py` / `dl_sogou2.py`：搜狗图片下载
- `inat.py`：iNaturalist 下载
- `validate_frames.py` / `classify_frames.py` / `classify_all.py` / `validate_imgs.py`：检测器+分类器自动标注
- `organize.py`：整理到 data/collected/
