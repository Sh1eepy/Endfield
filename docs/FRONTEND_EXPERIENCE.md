# Web 空间体验

> 更新日期：2026-09-12。本文描述当前实现；量化浏览器证据和未验证边界见 [空间升级验收](FRONTEND_SPATIAL_ACCEPTANCE.md)。

## 目标与边界

Web 保留终末地官网风格的角色拼贴、纸白/石墨/工业黄配色和原有查询结果组件，同时用程序化 3D 建立贯穿 Home、过渡区与 Query 的空间连续性。空间层只负责氛围、镜头和档案展示载体：不得绑定知识条目，不得产生配方或问答事实，不得遮挡来源、表格和操作按钮。

没有使用 RhineLabUI 的 Logo、档案数据、字体、声音或 GLB 模型。`transition.ts` 的临界阻尼计算参考其 MIT 源码，声明见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## 页面与动画生命周期

- `EntryCurtain`：约 6 秒，依次呈现终端连接、轨道扫描、欢迎标题与退场；8 秒硬超时。每个会话默认一次，可跳过、Esc 退出或手动重播；减少动态效果时直接进入页面。
- `ArchiveExperience`：拥有唯一 sticky canvas、React 查询/结果覆盖层、静态开关、可见性和 WebGL 生命周期。
- `Hero`：仍使用官方角色与本地地景；共享 canvas 的双螺旋在后方出现，角色、黄色色块及等高线向下渐隐。
- `archive-bridge`：桌面约 200px、手机约 130px；把首页地景、中央环和查询空间连续起来，不捕获滚轮或触摸。
- Query：配方模式为浅色工业空间，问答模式为石墨空间；标题、材质、背景和相机由同一 TransitionCoordinator 协调，切换模式不触发请求。

## 3D 场景

`archiveScene.ts` 动态导入 Three.js，只创建一个 renderer、scene、camera 和 EffectComposer：

- 56 个档案载体共享 `RoundedBoxGeometry` 与材质；玻璃主体为 3.2 × 1.6 × 0.42，金属框更薄；
- 双螺旋载体、骨架和横向连接使用同一参数函数；小幅半径波在高度方向传播，避免随机抖动和结构错位；
- 中段是半径 6.4 的主环和两条辅环；环是静态参照，螺旋围绕共同父级中心运动；
- 鼠标控制 yaw 约 ±0.58 rad、pitch 约 ±0.13 rad；页面每滚动一屏贡献约 0.22 rad 的缓慢 yaw，阵列浏览也产生更小的旋转；
- 指针、滚动、模式、浏览和抽取共用 TransitionCoordinator 的阻尼，不维护第二条时间轴；
- EffectComposer 的半浮点渲染目标使用设备允许范围内最高 4x MSAA；泛光限于低强度高亮，不模糊 DOM。

选中轮廓挂在载体本地坐标中。抽取开始时读取载体世界坐标与旋转；收回时接续阵列当前世界姿态。抽取期间停止指针更新，稳定阅读后停止 rAF，避免结果阅读时背景持续耗费 GPU。

## 查询反馈

提交后立即显示 `RetrievalStatus`，它消费现有 `phase_text`，显示真实阶段、不确定进度条和已等待秒数。未收到阶段事件时只写“等待服务响应”，不编造百分比、命中数或预计结束时间。10 秒后提示可以继续等待或停止生成。

SSE 的 `phase`/`meta` 不会使反馈提前结束；正文出现后档案只抽取一次。结果面板开始显现后，“档案内容已就绪”和“跳过抽取”隐藏，防止覆盖正文；停止、错误、重试和收回仍是 DOM 可访问控件。

## 降级与性能

- Three.js 仅在空间进入视口、页面可见且允许动态效果时加载；切到静态场景会释放 renderer；
- WebGL 不可用、初始化失败或上下文丢失时，保留官方地景/纹理和全部业务交互；新增几何、材质、环境图与 composer 均在 `dispose()` 释放；
- 手机保持 `touch-action: pan-y`，触摸 pointer 不驱动 3D，也不启用阵列拖动；使用静态构图和 ↑↓ 按钮浏览；
- 浏览状态允许低速连续动画；档案稳定展开、离开视口或标签页进入后台后停帧；
- 不承诺固定 60fps、固定功耗降低百分比或真机风扇表现。当前动态场景包约 566KB（gzip 约 142KB），仍有 Vite 大包提示；中文字体约 17.8MB，未做不安全子集化。

## 不变量与维护入口

- 业务状态仍由 `App.tsx` 管理：两个模式的草稿与缓存独立；切换不查询；新请求可取消旧请求；配方只读 `output/recipes.json`；
- `ArchiveExperience.tsx` 管理 DOM/场景桥接，`scene/archiveScene.ts` 管理 Three.js，`scene/transition.ts` 管理运动状态，`scene/archiveGeometry.ts` 保存纯几何参数；
- 样式依次由 `experience.css`、`helix.css`、`entry-orbit.css`、`spatial-continuity.css` 扩展，后加载文件用于当前版本覆盖；
- 自动验证：`cd web; npm test; npm run build`，根目录运行 `python -m unittest tests.test_frontend_contract`；
- 浏览器验收：运行 [工具清单](TOOLS.md) 中的 `check_spatial_frontend.mjs`，同时检查 1440×900、390×844、鼠标拾取、抽取/收回、触摸策略、上下文丢失和减少动态效果。

## 已知边界

- 当前浏览器验收的问答使用本地延迟 SSE 模拟，不代表真实 LLM 首字延迟或答案质量；
- 尚未量测实体手机、长期显存、GPU 功耗和稳定帧时间；
- 浏览器截图与 JSON 是可重建验收产物，不进入普通 Git 历史；
- `FRONTEND_SPATIAL_ACCEPTANCE.md` 是本轮证据快照；代码和本文是后续维护的当前事实来源。
