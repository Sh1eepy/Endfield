// pages/operator/operator.js — 干员详情页（阶段 4：章节/Tab/宽表/音频）
// 数据来自 /api/synthesis 的 kb.operator_detail（结构化，不经 RAG 切片）
// 结构：chapters[].widgets[].{facts, tabs[].{intro, blocks, audios}}

const api = require('../../utils/api');

// 块渲染辅助：sections_struct 的块类型 → 小程序可渲染数据
// 网页端 renderStructBlocks 处理 para/img/table/hr/video，这里映射为统一结构

// 图片 URL 统一走 /api/media 白名单代理（绕开 WIKI CDN 防盗链，与网页端 mediaSrc 一致）
function media(url) {
  const u = String(url || '');
  if (!u) return '';
  if (u.startsWith('https://bbs.hycdn.cn/image/') || u.startsWith('https://bbs.hycdn.cn/audio/')) {
    return api.mediaUrl(u);
  }
  return u;
}

function mapBlock(b) {
  if (!b) return null;
  if (b.t === 'para') return { t: 'para', inline: mapInline(b.c || []) };
  if (b.t === 'img') return { t: 'img', u: media(b.u), alt: b.alt || '' };
  if (b.t === 'table') {
    const rows = (b.r || []).map(row => (row || []).map(cell => mapInline(cell || [])));
    // 检测是否为"图片表格"（干员履历/待机动作/物料等：单元格主要是 img）
    let imgCount = 0, cellCount = 0;
    rows.forEach(row => row.forEach(cell => {
      cellCount += cell.length;
      imgCount += cell.filter(e => e.t === 'img').length;
    }));
    const isImgTable = cellCount > 0 && imgCount / cellCount >= 0.5;
    return { t: 'table', rows, isImgTable };
  }
  if (b.t === 'hr') return { t: 'hr' };
  if (b.t === 'video') {
    // 原始数据若带 HTTPS 直链则交给原生 <video>；只有森空岛 ID 时保留文章入口。
    const direct = String(b.url || b.videoUrl || b.src || b.resourceUrl || '');
    return {
      t: 'video', id: b.id,
      playUrl: direct.startsWith('https://') ? direct : '',
      poster: media(b.poster || b.cover || ''),
      videoUrl: 'https://www.skland.com/article?id=' + encodeURIComponent(String(b.id || '')),
    };
  }
  return null;
}

// inline 块（text/entry/link/img）→ 简单文本节点数组
// entry 物品引用带 ×数量 + 图标（对齐网页 renderInline：`图标 名称×数量`）
function mapInline(cells) {
  return (cells || []).map((e) => {
    if (!e) return { t: 'text', v: '' };
    if (e.t === 'text') return { t: 'text', v: String(e.x || ''), b: !!e.b, color: e.color || '' };
    if (e.t === 'entry') {
      const cnt = e.c;
      let cntStr = '';
      // c=0 表示"无数量含义"（速览/武器等仅列出名称），不显示 ×0；
      // 仅 c>0 时格式化显示（1600.0 → 1600，1.5 保留小数）
      if (cnt !== undefined && cnt !== null && cnt !== '' && Number(cnt) > 0) {
        const n = Number(cnt);
        cntStr = (Number.isInteger(n) && Math.abs(n) < 1e12) ? String(Math.trunc(n)) : String(n);
      }
      return { t: 'entry', v: String(e.x || ''), c: cntStr, icon: e.img ? media(e.img) : '' };
    }
    if (e.t === 'link') return { t: 'link', v: String(e.x || ''), u: e.u };
    if (e.t === 'img') return { t: 'img', u: media(e.u) };
    return { t: 'text', v: '' };
  });
}

Page({
  data: {
    name: '',
    loading: false,
    error: '',
    op: null,             // 完整 operator_detail
    visual: '',           // 立绘
    chapters: [],         // [{title, active}]
    activeChapter: 0,
    // 当前章节 widgets（预计算）
    widgets: [],
    // 音频
    playingIdx: '',       // 当前播放的音频 key
  },

  _audioCtx: null,

  onLoad(options) {
    const name = options.name ? decodeURIComponent(options.name) : '';
    this.setData({ name });
    if (name) this.loadOperator(name);
  },

  onUnload() {
    if (this._audioCtx) { this._audioCtx.destroy(); this._audioCtx = null; }
  },

  loadOperator(name) {
    this.setData({ loading: true, error: '', op: null });
    api.operator(name)
      .then((d) => {
        if (!d.ok || !d.no_recipe || !d.kb || !d.kb.operator_detail) {
          this.setData({ error: '未找到干员详情', loading: false });
          return;
        }
        const od = d.kb.operator_detail;
        const chapters = (od.chapters || []).map((c, i) => ({
          title: c.title,
          active: i === 0,
          // 过滤完全空 widget（无 facts/tabs/内容），避免空白框
          widgets: (c.widgets || []).map(w => this._mapWidget(w)).filter(w =>
            w.facts.length || w.tabs.length || (w.title && w.type)),
        }));
        this.setData({
          op: od,
          visual: media(od.illustration || od.cover || ''),
          chapters,
          activeChapter: 0,
          loading: false,
        });
        this._syncWidgets();
      })
      .catch((e) => this.setData({ error: e.message || '请求失败', loading: false }));
  },

  // 单个 widget → 小程序数据结构（facts + tabs）
  _mapWidget(w) {
    const facts = (w.facts || []).map(f => ({ label: f.label, value: f.value }));
    const tabs = (w.tabs || []).map((t, ti) => ({
      title: t.title || '页签 ' + (ti + 1),
      icon: media(t.icon || ''),
      active: ti === 0,
      intro: t.intro ? {
        imgUrl: media(t.intro.imgUrl || ''),
        name: t.intro.name || '',
        type: t.intro.type || '',
        description: t.intro.description || '',
      } : null,
      // 合并相邻 para 块（减少"潜能说明"等碎段落造成的空白），表格/图片/视频保持独立
      blocks: this._mergeParas((t.blocks || []).map(mapBlock).filter(Boolean)),
      audios: (t.audios || []).map(a => ({ url: a.url, title: a.title, profile: a.profile })),
    }));
    return {
      title: w.title || '',
      type: w.type || 'DATA',
      facts,
      tabs,
      hasTabs: tabs.length > 1 || (tabs.length === 1 && tabs[0].icon),
    };
  },

  // 合并连续 para：相邻段落拼成一个（\n 分隔），消除碎段空白
  _mergeParas(blocks) {
    const out = [];
    for (const b of blocks) {
      if (b && b.t === 'para' && out.length && out[out.length - 1].t === 'para') {
        out[out.length - 1].inline.push({ t: 'text', v: '\n' });
        out[out.length - 1].inline = out[out.length - 1].inline.concat(b.inline);
      } else {
        out.push(b);
      }
    }
    return out;
  },

  // 同步当前章节的 widgets 到 data（简化 WXML 遍历）
  _syncWidgets() {
    const ch = this.data.chapters[this.data.activeChapter];
    this.setData({ widgets: ch ? ch.widgets : [] });
  },

  // ===== 交互 =====
  // 章节切换
  onChapterTap(e) {
    const i = Number(e.currentTarget.dataset.i);
    if (i === this.data.activeChapter) return;
    const chapters = this.data.chapters.map((c, ci) => ({ ...c, active: ci === i }));
    this.setData({ chapters, activeChapter: i });
    this._syncWidgets();
  },

  // Tab 切换（widget 内部）
  onTabTap(e) {
    const wi = Number(e.currentTarget.dataset.wi);
    const ti = Number(e.currentTarget.dataset.ti);
    const widgets = this.data.widgets.map((w, idx) => {
      if (idx !== wi || !w.tabs.length) return w;
      return { ...w, tabs: w.tabs.map((t, j) => ({ ...t, active: j === ti })) };
    });
    this.setData({ widgets });
  },

  // 音频播放
  onAudioTap(e) {
    const key = e.currentTarget.dataset.key;
    const url = e.currentTarget.dataset.url;
    if (!this._audioCtx) this._audioCtx = wx.createInnerAudioContext();
    if (this.data.playingIdx === key) {
      this._audioCtx.stop();
      this.setData({ playingIdx: '' });
      return;
    }
    this._audioCtx.stop();
    this._audioCtx.src = api.mediaUrl(url);
    this._audioCtx.play();
    this.setData({ playingIdx: key });
    this._audioCtx.onEnded(() => this.setData({ playingIdx: '' }));
    this._audioCtx.onError(() => this.setData({ playingIdx: '' }));
  },

  // 图片失败兜底
  onImgError(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ [key]: true });
  },

  // 图片全屏预览（wx.previewImage）
  onImgPreview(e) {
    const url = e.currentTarget.dataset.url;
    if (!url) return;
    wx.previewImage({ current: url, urls: [url] });
  },

  // 条目引用点击：跳转到该条目的查询页
  // ask 页 mode=syn 会自动分发：干员→详情页 / 物品设备→合成树 / 速览→知识库信息
  onEntryTap(e) {
    const name = e.currentTarget.dataset.name;
    if (!name) return;
    wx.navigateTo({ url: '/pages/ask/ask?q=' + encodeURIComponent(name) + '&mode=syn' });
  },

  // 视频跳转（森空岛文章页）
  onVideoTap(e) {
    const url = e.currentTarget.dataset.url;
    if (!url) return;
    wx.setClipboardData({
      data: url,
      success: () => {
        wx.showModal({
          title: '视频链接已复制',
          content: '已在剪贴板，请用浏览器打开森空岛文章查看视频（小程序无法内嵌播放）',
          showCancel: false,
        });
      },
    });
  },
});
