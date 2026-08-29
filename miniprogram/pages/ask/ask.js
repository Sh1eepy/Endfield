// pages/ask/ask.js — 问答结果页（阶段 3：完整渲染）
// 行为对齐网页端 renderAsk：
//   - structured 直查 → 配方卡/设备卡/产物反查/歧义候选
//   - 知识库检索 → 意图标签 + 答案（引用角标可点）+ 来源 chips + 片段折叠
// 手机竖屏：单列堆叠。

const api = require('../../utils/api');
const { mdToNodes } = require('../../utils/markdown');

Page({
  data: {
    query: '',
    mode: 'ask',          // ask=知识问答 / syn=配方（合成树）
    loading: false,
    error: '',
    result: null,
    // 合成树模式
    synthTree: null,      // /api/synthesis 返回的 tree
    kbData: null,
    // 结构化直查渲染用
    route: '',            // recipe / device / device_products / ambiguous
    recipeCard: null,     // {title, recipes:[{machine,duration,inputs,outputs}]}
    deviceProducts: null, // {keyword, matches:[{device,output,count}]}
    ambiguous: null,      // {item, candidates:[]}
    // 知识库检索渲染用
    intent: '',
    routeTag: '',
    answerSegs: [],       // 解析 [来源N] 后的分段 [{t:'md', nodes} | {t:'ref', v, n}]（md 段经 markdown 渲染）
    rejected: false,
    sources: [],
    hits: [],             // [{name, category, text}]
    hitsOpen: false,
    highlightSrc: 0,      // 高亮来源序号（引用角标点击后短暂高亮）
    feedbackState: 'idle', // idle / sending / sent / error
  },

  onLoad(options) {
    const q = options.q ? decodeURIComponent(options.q) : '';
    const mode = options.mode === 'syn' ? 'syn' : 'ask';
    this.setData({ query: q, mode });
    if (q) {
      if (mode === 'syn') {
        // 配方模式：先探测是否为干员（有 operator_detail → 跳详情页）
        this._probeOperator(q);
      } else {
        this.runAsk(q);
      }
    }
  },

  _beginQuery() {
    this._queryId = (this._queryId || 0) + 1;
    this.setData({
      loading: true, error: '', result: null, synthTree: null, kbData: null,
      route: '', recipeCard: null, deviceProducts: null, ambiguous: null,
      intent: '', routeTag: '', answerSegs: [], rejected: false,
      sources: [], hits: [], hitsOpen: false, highlightSrc: 0,
      feedbackState: 'idle',
    });
    return this._queryId;
  },

  onUnload() {
    this._queryId = (this._queryId || 0) + 1;
  },

  // 探测：/api/synthesis 若返回 no_recipe + operator_detail，说明是干员 → 跳详情
  _probeOperator(q) {
    const queryId = this._beginQuery();
    return api.operator(q)
      .then((d) => {
        if (queryId !== this._queryId) return;
        if (d.ok && d.no_recipe && d.kb && d.kb.operator_detail) {
          wx.redirectTo({ url: '/pages/operator/operator?name=' + encodeURIComponent(q) });
          return;
        }
        // 非干员 → 直接复用探测结果渲染（避免二次请求）
        this._renderSynResult(q, d);
      })
      .catch(() => {
        if (queryId === this._queryId) return this._loadSynTree(q, queryId);
      });
  },

  // 渲染 /api/synthesis 结果（合成树/设备/歧义/知识库）
  _renderSynResult(q, d) {
    this.setData({ loading: false });
    if (!d.ok) {
      this.setData({ error: d.error || '未找到' });
      return;
    }
    if (d.ambiguous) {
      this.setData({ route: 'ambiguous', ambiguous: { item: d.item, candidates: d.candidates || [] } });
      return;
    }
    if (d.tree && d.tree.kind === 'device') {
      this.setData({
        route: 'device',
        recipeCard: { title: `设备「${d.tree.name}」能造的配方（${(d.tree.recipes || []).length} 个）`, recipes: d.tree.recipes || [] },
      });
      return;
    }
    if (d.no_recipe && d.kb) {
      if (d.kb.operator_detail) {
        wx.redirectTo({ url: '/pages/operator/operator?name=' + encodeURIComponent(q) });
        return;
      }
      // 关键：必须经过 _buildKbData 转换（生成 sections 数组 + fullBlocks），
      // 否则 WXML 用 kbData.sections.length 会因 undefined 而不渲染 → 空白
      this.setData({ route: 'kb', kbData: this._buildKbData(d.kb) });
      return;
    }
    if (d.tree) {
      this.setData({ synthTree: d.tree });
    } else {
      this.setData({ error: '未找到相关数据' });
    }
  },

  // 加载合成树
  _loadSynTree(q, queryId = this._beginQuery()) {
    return api.synthesis(q, 10)
      .then((d) => {
        if (queryId === this._queryId) this._renderSynResult(q, d);
      })
      .catch((e) => {
        if (queryId === this._queryId) this.setData({ error: e.message || '请求失败', loading: false });
      });
  },

  // 合成树叶子点击 → 重新搜索
  onTreeSearch(e) {
    const name = e.detail.name;
    if (!name) return;
    this.setData({ query: name });
    this._probeOperator(name);
  },

  // 组织知识库回退数据：sections/sections_struct → 带标题的内容列表（完整渲染）
  _buildKbData(kb) {
    const name = (kb && kb.name) || '';
    const category = (kb && kb.category) || '';
    const sections = [];
    const ss = (kb && kb.sections_struct) || {};
    const secTexts = (kb && kb.sections) || {};
    const keys = Object.keys(ss).length ? Object.keys(ss) : Object.keys(secTexts);
    keys.slice(0, 20).forEach((k) => {
      const blocks = ss[k];
      if (Array.isArray(blocks) && blocks.length) {
        sections.push({ title: k, blocks: blocks.map(this._mapBlock).filter(Boolean) });
      } else if (secTexts[k] && String(secTexts[k]).trim()) {
        sections.push({ title: k, blocks: [{ t: 'para', text: String(secTexts[k]) }] });
      }
    });
    // full_text 兜底：解析 [图片](url) 标记为真图，文本完整显示
    const fullText = (kb && kb.full_text) || '';
    return { name, category, sections, fullText, fullBlocks: this._parseFullText(fullText) };
  },

  // 解析 full_text：把 [图片](url) 拆出来，其余为段落（图片 URL 走 /api/media 代理绕防盗链）
  _parseFullText(text) {
    if (!text) return [];
    const blocks = [];
    const re = /\[图片\]\(([^)]+)\)/g;
    let last = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last && text.slice(last, m.index).trim()) {
        blocks.push({ t: 'para', text: text.slice(last, m.index).trim() });
      }
      blocks.push({ t: 'img', u: this._mediaUrl(m[1]) });
      last = m.index + m[0].length;
    }
    if (last < text.length && text.slice(last).trim()) {
      blocks.push({ t: 'para', text: text.slice(last).trim() });
    }
    return blocks;
  },

  // 图片 URL 走 /api/media 代理（bbs.hycdn.cn 防盗链）
  _mediaUrl(url) {
    const u = String(url || '');
    if (u.startsWith('https://bbs.hycdn.cn/image/') || u.startsWith('https://bbs.hycdn.cn/audio/')) {
      return api.mediaUrl(u);
    }
    return u;
  },

  // kb 结构化块映射（文本/表格/图片）
  _mapBlock(b) {
    if (!b) return null;
    if (b.t === 'para') {
      const texts = (b.c || []).map(e => {
        if (!e) return '';
        if (e.t === 'text') return String(e.x || '');
        if (e.t === 'entry') return String(e.x || '');
        return '';
      }).join('');
      return { t: 'para', text: texts };
    }
    if (b.t === 'table') {
      return { t: 'table', rows: (b.r || []).map(row => (row || []).map(cell => {
        // 单元格内可能有多段 inline
        return (cell || []).map(e => {
          if (!e) return '';
          if (e.t === 'text') return String(e.x || '');
          if (e.t === 'entry') return String(e.x || '');
          return '';
        }).join('');
      })) };
    }
    if (b.t === 'img') return { t: 'img', u: b.u };
    if (b.t === 'hr') return { t: 'hr' };
    return null;
  },

  runAsk(q) {
    const queryId = this._beginQuery();
    return api.ask(q, 5, true)
      .then((d) => {
        if (queryId !== this._queryId) return;
        if (!d.ok) {
          this.setData({ error: d.error || '问答失败', loading: false });
          return;
        }
        this._render(d);
      })
      .catch((e) => {
        if (queryId === this._queryId) this.setData({ error: e.message || '请求失败', loading: false });
      });
  },

  // ===== 渲染分发 =====
  _render(d) {
    const patch = { loading: false, result: d };
    if (d.route_used === 'structured') {
      // 结构化直查：配方/设备/产物反查/歧义
      if (d.route === 'recipe') {
        patch.route = 'recipe';
        patch.recipeCard = {
          title: `「${d.item}」的合成配方`,
          recipes: d.recipes || [],
        };
      } else if (d.route === 'device') {
        patch.route = 'device';
        patch.recipeCard = {
          title: `设备「${d.device}」能造的配方（${(d.recipes || []).length} 个）`,
          recipes: d.recipes || [],
        };
      } else if (d.route === 'device_products') {
        patch.route = 'device_products';
        patch.deviceProducts = { keyword: d.keyword, matches: d.matches || [] };
      } else if (d.route === 'ambiguous') {
        patch.route = 'ambiguous';
        patch.ambiguous = { item: d.item, candidates: d.candidates || [] };
      }
    } else {
      // 知识库检索
      patch.route = 'rag';
      patch.intent = d.intent || '未知';
      patch.routeTag = d.route_used === 'structured' ? '结构化直查' : '知识库检索';
      patch.rejected = !!d.rejected;
      patch.answerSegs = this._parseRefs(d.answer || (d.rejected
        ? '知识库中未找到足够相关的资料来回答这个问题。'
        : '（回答生成暂不可用）'));
      patch.sources = (d.sources || []).map((s, i) => ({ n: i + 1, name: s.name, category: s.category || '' }));
      patch.hits = (d.hits || []).map(h => ({
        name: h.meta && h.meta.name || '',
        category: h.meta && h.meta.category || '',
        text: String(h.text || '').slice(0, 260),
      }));
    }
    this.setData(patch);
  },

  // 解析 [来源N] 成可点击角标分段（对齐网页 escRef）；
  // plain 段内容经 markdown 解析器转成 rich-text nodes，避免 **、* 等符号原样暴露
  _parseRefs(answer) {
    const segs = [];
    const re = /\[来源(\d+)\]/g;
    let last = 0;
    let m;
    while ((m = re.exec(answer)) !== null) {
      if (m.index > last) segs.push({ t: 'md', nodes: mdToNodes(answer.slice(last, m.index)) });
      segs.push({ t: 'ref', v: `[${m[1]}]`, n: parseInt(m[1], 10) });
      last = m.index + m[0].length;
    }
    if (last < answer.length) segs.push({ t: 'md', nodes: mdToNodes(answer.slice(last)) });
    if (!segs.length) segs.push({ t: 'md', nodes: mdToNodes(answer) });
    return segs;
  },

  // ===== 交互 =====
  // 答案分段点击：仅 ref 段触发来源高亮
  onSegTap(e) {
    if (e.currentTarget.dataset.t !== 'ref') return;
    const n = Number(e.currentTarget.dataset.n) || 0;
    if (!n) return;
    this.setData({ highlightSrc: n });
    wx.pageScrollTo({ selector: '#sources-anchor', offsetTop: -90, duration: 400 });
    setTimeout(() => this.setData({ highlightSrc: 0 }), 1600);
  },

  // 检索片段折叠开关
  onHitsToggle() {
    this.setData({ hitsOpen: !this.data.hitsOpen });
  },

  onFeedback(e) {
    const vote = e.currentTarget.dataset.vote;
    const result = this.data.result;
    if (!result || !result.trace_id || !this.data.query ||
        this.data.feedbackState === 'sending' || this.data.feedbackState === 'sent') return;
    this.setData({ feedbackState: 'sending' });
    return api.feedback(result.trace_id, this.data.query, vote, '', result.feedback_snapshot || '')
      .then(() => this.setData({ feedbackState: 'sent' }))
      .catch(() => this.setData({ feedbackState: 'error' }));
  },

  // 歧义候选 → 按当前模式查询，配方模式不能走知识问答 API。
  onAmbiguousPick(e) {
    const name = e.currentTarget.dataset.name;
    if (!name) return;
    this.setData({ query: name });
    return this.data.mode === 'syn' ? this._probeOperator(name) : this.runAsk(name);
  },

  // kb 页图片全屏预览
  onKbImgPreview(e) {
    const url = e.currentTarget.dataset.url;
    if (!url) return;
    wx.previewImage({ current: url, urls: [url] });
  },

  // 来源 chip 点击：干员 → 干员详情页；否则 → 合成树结果页
  onSourceTap(e) {
    const name = e.currentTarget.dataset.name;
    const cat = e.currentTarget.dataset.cat || '';
    if (cat === '干员' || cat === '干员攻略') {
      wx.navigateTo({ url: '/pages/operator/operator?name=' + encodeURIComponent(name) });
    } else {
      wx.navigateTo({ url: '/pages/ask/ask?q=' + encodeURIComponent(name) + '&mode=syn' });
    }
  },
});
