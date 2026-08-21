// utils/theme.js — 视觉 token（JS 侧使用，与 app.wxss 保持一致）
// 供 canvas 绘制（合成树）与动态样式计算使用。

module.exports = {
  colors: {
    bg: '#F5F4EE',
    card: '#FFFFFF',
    panel: '#F0EFE8',
    panel2: '#E7E6DF',
    border: '#D5D4CC',
    border2: '#AAA99F',
    accent: '#F0CF16',
    accent2: '#232722',
    accent3: '#796A00',
    text: '#171916',
    sub: '#61665D',
    faint: '#969A91',
    ink: '#111310',
    paper: '#FFFFFF',
    yellow: '#F0CF16',
    klein: '#1737D1',
    kleinSoft: 'rgba(23,55,209,0.18)',
    depth: '#B8B5A8',
    ok: '#6DA900',
    danger: '#FF6B57',
    nodeBg: '#FFFFFF',
    nodeStroke: '#242822',
    nodeStrokeHover: '#F0CF16',
    nodeLabel: '#20231F',
    nodeSub: '#777B73',
    link: '#A8ABA3',
    linkCnt: '#8D7C0E',
    edgeLabel: '#665B0B',
  },
  font: {
    cn: 'sans-serif', // 小程序 canvas 用系统字体；标题近似加粗
    tech: 'monospace', // 等宽：canvas 无自定义字体时用 monospace 近似
  },
};
