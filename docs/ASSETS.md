# 素材清单、数据来源与免责声明

本文是项目唯一的来源追溯与合规说明。产品使用的每一类内容——美术素材、字体、知识数据、第三方代码与生成物——都在这里记录来源、性质与使用边界。新增任何素材或数据源之前，先读本文并在对应小节补一行。

## 1. 素材清单与来源登记

正式记录在 `web/assets/official/sources.json`：每个文件的来源 URL、字节数与 SHA256 一一对应，可用脚本核对。

| 文件 | 来源 | 主体 |
|---|---|---|
| `talos-keyvisual.jpg` | `web.hycdn.cn/endfield/official-v4/.../kv-obt-pc.*.jpg` | 鹰角网络官网 |
| `perlica-portrait.png` 等 5 张干员立绘 | 同上，`official-v4/_next/static/media/` | 鹰角网络官网 |
| `home-background.jpg`、`divider.png`、`texture.png`、`wave.png`、`landscape.jpg` | 同上 | 鹰角网络官网 |
| `query-orbit.jpg` | `gmedia.playstation.com`（PlayStation 官方产品页展示图） | **索尼互动娱乐页面**，非鹰角直接发布 |

- 公开来源为《明日方舟：终末地》官网 `https://endfield.hypergryph.com/`。下载脚本 `scripts/fetch_official_design_assets.py` 只保存选定公开图片，不执行官网 JavaScript，运行期不依赖官网 CDN；官网样式与页面快照仅作设计证据，不进入产品运行链路；素材在使用时经过 CSS 去色、渐变遮罩、透明度与裁切处理，原图不修改；
- **游戏徽标** `endfield-logo.png` 来自官方网站，经项目使用者确认，文件指纹已记入 `sources.json`：网页端 1324×1188（带透明通道，约 515 KB），小程序端为同一徽标的 100×90 版本（约 2 KB）。具体直链未记录，补记时替换 `sources.json` 中的 `source` 字段即可；
- **未使用的吉祥物图**：`web/assets/mascots/mascot-01.png` 至 `mascot-08.png` 与 `miniprogram/assets/images/mascot-01.png` 至 `mascot-08.png` 没有可追溯的来源记录，且**代码中没有任何引用**。这些文件**已从版本控制移除并加入 `.gitignore`**，本地保留副本以备查，不随仓库分发；如要使用，必须先确认出处、补记来源与 SHA256，再取消忽略。`web/assets/official/` 下正式登记的素材不受影响。

## 2. 字体许可

| 字体 | 文件 | 许可 | 许可文本 |
|---|---|---|---|
| Noto Sans SC | `web/assets/fonts/NotoSansSC-Variable.ttf`（约 17.4 MB） | SIL Open Font License 1.1 | `web/assets/fonts/OFL-NotoSansSC.txt` |
| Oxanium | `web/assets/fonts/Oxanium-Variable.ttf` | SIL Open Font License 1.1 | `web/assets/fonts/OFL-Oxanium.txt` |

OFL 允许自由使用、修改与再分发，条件是保留许可文本且不得单独售卖字体本身。项目已随字体附带许可文件，构建产物中不包含许可文本——如需在分发物中体现，应将两份 OFL 文件一并保留在仓库与发布说明中。小程序侧只使用 `Oxanium-Variable.ttf`，未打包中文字体以控制包体。

## 3. 第三方代码与算法

| 项目 | 用途 | 许可 |
|---|---|---|
| RhineLabUI 的临界阻尼算法 | `web/src/scene/transition.ts` 的阻尼实现（改编自 RhineLabUI `src/motion.ts`） | MIT，版权归 Copyright (c) 2026 LBEILC，许可全文见本节末 |
| Three.js、React、Vite、Framer Motion 等 | 运行时依赖 | 各自的 MIT 类许可，版本见 `web/package.json` |

项目**没有**导入 RhineLabUI 的品牌素材、档案数据、字体、音效或 GLB 模型，也没有导入官网视频、第三方品牌模型或官网字体。3D 双螺旋、档案盒与中央环均为程序化几何生成，不是任何官方模型的复刻。

RhineLabUI 的 MIT 许可要求在下游副本中保留版权声明与许可文本，完整条文如下：

```text
MIT License
Copyright (c) 2026 LBEILC
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 4. 知识数据来源与分层

内容按性质分三类：**事实与数值**（配方、材料数量、设备参数、物品名称，通常不受著作权保护，自由整理与再分发、仅用于查询）、**作品（表达）**（角色立绘、宣传主视觉、游戏徽标、字体文件，受著作权保护，记录来源、保持署名、非商业使用）、**第三方代码**（各自许可，保留许可文本与声明）。

| 层级 | 位置 | 性质 | 来源 |
|---|---|---|---|
| 原始事实 | `endfield_wiki_full_2026-09-14.json`（约 168.7 MB）；上一版 `endfield_wiki_full_2026-08-07.json`（约 147.6 MB）保留作差分对照 | 只读快照，不入版本控制 | 官方 WIKI `wiki.skland.com/endfield` 公开条目，通过站点接口 `zonai.skland.com/web/v1/wiki/*` 在登录会话内采集 |
| 规范化知识 | `endfield_kb/`（45 个文件，约 15.1 MB） | 脚本生成 | 由事实源经 `build_kb_all.py` 解析为 22 个分类 |
| 结构化产物 | `output/recipes.json`、`item_media.json`、`operator_details.json` | 脚本生成 | 配方、媒体索引、干员详情 |
| 检索产物 | `output/rag/`、`output/mention_index.json`、`output/knowledge_graph/graph.db` | 脚本生成 | 向量索引、词法索引与知识图谱 |
| 评测产物 | `output/eval/` | 评测工具生成 | 回归基线 |

当前事实源于 **2026-09-14** 采集：2,229 个条目，详情抓取成功 2,229 条，失败 0 条，稳定 ID 无缺失或重复；与 2026-08-07 快照相比新增 284、下线 13、变化 1,040（差分见 `output/update_20260914/wiki_delta.json`）。采集范围限于公开可访问的条目与详情，未绕过任何访问控制。事实源与既有历史导出物只读，采集与解析脚本不修改上游数据。

**项目不收录的内容**：游戏音乐与音效、过场影像、完整剧情文本、官网整站镜像、浏览器缓存、无法说明来源的文件。产品界面没有音频播放功能。

## 5. 数据性质与使用边界

- 配方、材料数量、设备参数、物品名称等属于**游戏机制事实**，项目对其进行结构化整理，用于查询与检索；
- 条目中的**描述性文本**来自 WIKI 公开条目，属于表达性内容。项目仅将其用于检索问答：回答由模型依据检索片段生成，产品**不提供整篇原文浏览、导出或批量下载**；
- 项目**不声称**对上述数据享有任何权利，也不对数据的完整性、时效性或准确性作担保。游戏内容以官方发布为准；
- WIKI 条目可能由社区编辑维护，可能存在错漏。发现错误应提示使用者核对官方信息，而不是自动改写来源数据；
- 素材与业务解耦：素材缺失只影响视觉，不影响配方、检索或问答结果，页面必须有兜底样式。

## 6. 采集与再分发的自我约束

- 公开仓库不包含全量抓取副本、浏览器缓存或整站快照（见 `.gitignore`），不提交无法说明来源的文件；
- 不提供数据批量导出接口，不开放整库下载；
- 采集频率保持克制，不构成对上游站点的压力；只下载选定公开图片；
- 小程序只复制实际使用的素材，发布前检查主包与分包体积上限；
- 上游站点或权利方提出要求时，立即停止相关内容的采集与展示，并删除对应产物；
- 新增素材、数据源或第三方代码时：记录来源 URL、获取时间、字节数与 SHA256 → 判断内容性质并登记 → 确认产品确实使用该内容 → 更新本文件与页脚署名。

## 7. 免责声明

1. **非官方性质**：本项目是爱好者制作的**非官方社区工具**，与《明日方舟：终末地》的开发商、发行商及官方 WIKI 运营方**没有任何隶属、合作或授权关系**；
2. **权利归属**：游戏名称、角色、图像、文本及其他内容的权利归原权利方所有。项目对相关素材的使用不构成权利主张，也不代表权利方的认可；
3. **非商业用途**：项目**不收费、不含广告、不接受与内容相关的赞助**，仅用于学习、技术交流与个人查询。使用者不得将本项目或其数据用于商业目的；
4. **内容准确性**：数据来自公开 WIKI 条目的整理，可能存在**遗漏、滞后或错误**。项目不对任何查询结果作准确性担保。涉及游戏内决策时，请以官方游戏内信息与官方公告为准；
5. **模型输出**：知识问答由模型依据检索到的片段生成，**可能产生不完整或不准确的表述**。回答中标注了来源以便核对，使用者应自行判断，不应将其视为官方说明；
6. **责任限制**：因使用本项目或其数据产生的任何直接或间接损失，项目作者不承担责任；
7. **移除请求**：权利方如认为本项目使用的任何素材或内容不妥，请通过仓库 Issue 联系。**收到有效通知后，项目将立即下架相关内容**，无需争议前置程序。

产品页面页脚保持以下说明，不得删除或弱化，小程序端同样保留"非官方"说明与来源提示：`ENDFIELD ARCHIVE / 非官方社区工具`、美术素材与数据来源与权利归属提示、指向本文的链接。

界面视觉、布局、动效与三维场景代码，数据管道、检索编排、知识图谱构建与评测脚本，以及文档与图表，均由本项目自行实现；生成式模型参与编写的代码，其许可与责任由本项目承担。本文档是项目对自身内容来源的**如实记录与使用声明**，不构成法律意见；著作权与许可的具体适用因地区与个案而异，如涉及商业使用、公开发布或权利争议，请咨询专业人士。
