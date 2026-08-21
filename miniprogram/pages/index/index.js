// pages/index/index.js — 首页：搜索联想 + 历史 + 模式切换
// 行为对齐网页端 index.html：
//   - /api/names 全量联想（前缀优先 + 包含匹配，最多 14 条，命中词高亮）
//   - 搜索历史存本地（最多 8 条，含模式，点击恢复并执行，可清除）
//   - 配方/问答两种模式各自记忆查询词

const api = require('../../utils/api');

const HISTORY_KEY = 'endfield-mini-history-v1';
const HISTORY_LIMIT = 8;
const SUGGEST_LIMIT = 14;

Page({
  data: {
    backendOk: false,
    backendText: '后端未连接',
    mode: 'syn',
    query: '',
    // 开场动画
    curtainShow: true,
    // 滚动视差（scrollY 驱动几何体位移/缩放/旋转）
    parallax: 0,
    geoA: 'rotate(45deg)',
    geoB: 'skewX(-12deg)',
    geoC: 'rotate(-18deg)',
    geoD: '',
    // 联想
    suggest: [],          // 当前联想列表
    suggestShow: false,
    suggestActive: -1,    // 键盘上下选中
    suggestEmpty: false,  // 无匹配提示
    // 历史
    history: [],
    // 统计（hero）
    stats: { names: '--', recipes: '' },
  },

  _modeQueries: { syn: '', ask: '' }, // 各模式独立记忆；首次进入均为空

  onLoad() {
    this.checkHealth();
    this.loadNames();
    this.loadStats();
    this.renderHistory();
  },

  // 滚动视差：几何体随滚动位移、缩放和旋转
  onPageScroll(e) {
    const y = e.scrollTop || 0;
    if (Math.abs(y - this._lastScroll) < 2) return;
    this._lastScroll = y;
    // 每个几何体：位移系数 + 缩放 + 旋转（滚动越多变化越大）
    this.setData({
      parallax: y,
      geoA: `translateY(${y * -0.12}px) rotate(${45 + y * 0.03}deg) scale(${1 + y * 0.0004})`,
      geoB: `translateY(${y * -0.18}px) skewX(${-12 + y * 0.02}deg) scale(${1 + y * 0.0003})`,
      geoC: `translateY(${y * 0.09}px) rotate(${-18 - y * 0.02}deg) scale(${1 - y * 0.0003})`,
      geoD: `translateY(${y * 0.13}px) rotate(${y * 0.04}deg) scale(${1 + y * 0.0005})`,
    });
  },

  // 开场动画结束 → 隐藏
  onCurtainComplete() {
    this.setData({ curtainShow: false });
  },

  onShow() {
    this.checkHealth();
  },

  // ===== 后端状态 =====
  checkHealth() {
    api.health()
      .then(() => this.setData({ backendOk: true, backendText: '后端已连接' }))
      .catch(() => this.setData({ backendOk: false, backendText: '后端未连接' }));
  },

  // ===== 名称联想数据 =====
  loadNames() {
    api.names()
      .then((d) => { this._allNames = d.names || []; })
      .catch(() => { this._allNames = []; });
  },

  loadStats() {
    api.names().then((d) => {
      this.setData({ 'stats.names': String(d.count || '--') });
    }).catch(() => {});
  },

  // ===== 模式切换（各自记忆 query）=====
  switchMode(e) {
    const mode = e.currentTarget.dataset.mode;
    if (mode === this.data.mode) return;
    // 保存当前模式 query，恢复目标模式 query
    this._modeQueries[this.data.mode] = this.data.query;
    this.setData({
      mode,
      query: this._modeQueries[mode] || '',
      suggest: [],
      suggestShow: false,
      suggestActive: -1,
    });
  },

  // ===== 输入 → 联想过滤（前缀优先 + 包含匹配）=====
  onQueryInput(e) {
    const q = e.detail.value;
    this.setData({ query: q });
    const trim = q.trim();
    if (!trim) {
      this.setData({ suggest: [], suggestShow: false, suggestActive: -1 });
      return;
    }
    const names = this._allNames || [];
    const starts = names.filter(n => n.startsWith(trim));
    const contains = names.filter(n => n.includes(trim) && !n.startsWith(trim));
    const list = [...starts, ...contains].slice(0, SUGGEST_LIMIT);
    // 预处理：每个联想项直接算好高亮分段，避免 WXML 内嵌方法调用
    const suggest = list.map(name => ({
      name,
      segs: this._buildSegs(name, trim),
    }));
    this.setData({
      suggest,
      suggestShow: true,
      suggestActive: -1,
      suggestEmpty: list.length === 0,
    });
  },

  // 高亮分段：命中词拆成 {t:'plain'|'hit', v} 数组（对齐网页 renderSuggest）
  _buildSegs(name, q) {
    if (!q) return [{ t: 'plain', v: name }];
    const idx = name.indexOf(q);
    if (idx < 0) return [{ t: 'plain', v: name }];
    const segs = [];
    if (idx > 0) segs.push({ t: 'plain', v: name.slice(0, idx) });
    segs.push({ t: 'hit', v: name.slice(idx, idx + q.length) });
    if (idx + q.length < name.length) segs.push({ t: 'plain', v: name.slice(idx + q.length) });
    return segs;
  },

  // 点击联想项
  pickSuggestion(e) {
    const name = e.currentTarget.dataset.name;
    this.setData({ query: name, suggest: [], suggestShow: false });
    this.execute();
  },

  // ===== 搜索历史 =====
  getHistory() {
    try {
      const v = wx.getStorageSync(HISTORY_KEY);
      const arr = Array.isArray(v) ? v : [];
      return arr.filter(x => x && x.q).slice(0, HISTORY_LIMIT);
    } catch (_) { return []; }
  },

  renderHistory() {
    this.setData({ history: this.getHistory() });
  },

  recordHistory(q, mode) {
    const clean = String(q || '').trim();
    if (!clean) return;
    const next = [{ q: clean, mode }, ...this.getHistory()
      .filter(x => x.q !== clean || x.mode !== mode)].slice(0, HISTORY_LIMIT);
    try { wx.setStorageSync(HISTORY_KEY, next); } catch (_) {}
    this.renderHistory();
  },

  onHistoryTap(e) {
    const idx = Number(e.currentTarget.dataset.index);
    const entry = this.getHistory()[idx];
    if (!entry) return;
    const mode = entry.mode === 'ask' ? 'ask' : 'syn';
    this._modeQueries[this.data.mode] = this.data.query;
    this._modeQueries[mode] = entry.q;
    this.setData({
      mode,
      query: entry.q,
      suggest: [], suggestShow: false, suggestActive: -1,
    });
    this.execute();
  },

  onHistoryClear() {
    try { wx.removeStorageSync(HISTORY_KEY); } catch (_) {}
    this.renderHistory();
  },

  // ===== 提交执行 =====
  execute() {
    const q = (this.data.query || '').trim();
    if (!q) return;
    const mode = this.data.mode;
    this.recordHistory(q, mode);
    this._modeQueries[mode] = q;
    if (mode === 'ask') {
      wx.navigateTo({ url: '/pages/ask/ask?q=' + encodeURIComponent(q) });
    } else {
      // 配方模式：阶段 6 接入 canvas 合成树；当前跳转 ask 页以 mode=syn 标识，
      // 由 ask 页按 mode 分发（阶段 6 前先展示 API 摘要）
      wx.navigateTo({ url: '/pages/ask/ask?q=' + encodeURIComponent(q) + '&mode=syn' });
    }
  },

  onSubmit() {
    this.execute();
  },
});
