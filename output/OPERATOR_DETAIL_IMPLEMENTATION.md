# 干员详情实现说明

## 数据

`build_operator_details.py` 从 WIKI 块式文档整理干员详情，输出 `output/operator_details.json`。数据保留：

- 基本信息和带颜色/粗细的富文本；
- 精英化、技能、天赋、潜能、档案等章节和 Tab；
- 材料、武器和其他条目的图片；
- 干员展示图、技能动态图、视频链接和多语种语音。

接口 `/api/synthesis?item=干员名` 会在知识库结果中附带 `operator_detail`。前端由
`renderOperatorDetail()` 渲染，不把复杂内容压成普通文本。

## 展示规则

- 章节和同类多段内容使用局部按钮切换；
- WIKI 颜色 token 映射到前端样式，主能力和副能力保持区别；
- 表格外层都有独立横向滚动容器和可拖动状态条；
- 媒体使用完整图库卡片，避免塞进标题区域；
- 音频通过当前页按钮播放，再次点击暂停；
- 远程 WIKI 媒体走受限代理，加载失败显示明确状态。

## 相关文件

- 构建：`scripts/build_operator_details.py`
- API：`scripts/api_server.py`
- 前端：`web/index.html`
- 数据测试：`tests/test_operator_details.py`
- 前端契约：`tests/test_frontend_contract.py`
