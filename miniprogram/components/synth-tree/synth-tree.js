// components/synth-tree/synth-tree.js — canvas 合成树（v3：框内显示 + 拖动缩放）
// 复刻网页端 D3 纵向树：
//   - 竖向树：根在上，逐层向下（x=兄弟按子树宽度，y=深度）
//   - canvas 固定为容器大小（框内），树内容通过 scale+offset 变换绘制
//   - 交互：单指拖动平移；双指捏合缩放（0.4x~3x）；点击节点折叠/展开；点击叶子搜索
//   - 初始缩放自适应：树宽超出容器时缩放到适配，不超出框

const NODE_W = 80;
const NODE_H = 80;
const LEVEL_Y = 208;    // 物品层层间距 = 配方(80) + 间距(48) + 子(80)，保证卡片互不重叠
const SIBLING_X = 112;  // 横向兄弟间距：大于节点宽 80，避免水平重叠
const MIN_SCALE = 0.3;
const MAX_SCALE = 3;

Component({
  properties: {
    tree: { type: Object, value: null, observer: '_onTreeChange' },
  },

  data: {
    canvasW: 320,
    canvasH: 480,
    frameH: 480,
    treeTitle: '',
    // 提示条（拖动/缩放提示）
    hint: '单指拖动 · 双指缩放',
  },

  lifetimes: {
    ready() {
      this._collapsed = new Set();
      this._imgCache = {};
      this._view = { scale: 1, ox: 0, oy: 0 }; // 视口变换
      this._drag = null;
      this._pinch = null;
      if (this.data.tree) this._scheduleRender();
    },
  },

  methods: {
    _onTreeChange(tree) {
      this._collapsed = new Set();
      this._view = { scale: 1, ox: 0, oy: 0 };
      this.setData({ treeTitle: (tree && tree.name) || '' });
      if (tree) this._scheduleRender();
    },

    _scheduleRender() {
      setTimeout(() => this._render(), 60);
    },

    // ===== 竖向 tidy 布局 =====
    _layout(root) {
      const nodes = [];
      const links = [];
      const collapsed = this._collapsed;

      function subWidth(n) {
        if (!n.recipes || !n.recipes.length) return 1;
        return (n.recipes || []).reduce((acc, r) =>
          acc + (r.inputs || []).reduce((a2, x) => a2 + subWidth(x), 0), 0);
      }

      function assign(n, key, depth, xStart, visible) {
        const hasChildren = Boolean(n.recipes && n.recipes.length);
        const w = subWidth(n);
        const x = xStart + (w * SIBLING_X) / 2;
        const y = depth * LEVEL_Y;
        const node = { key, node: n, x, y, depth, visible, hasChildren, children: [], isRecipe: false };
        nodes.push(node);

        if (visible && !collapsed.has(key) && hasChildren) {
          let cursor = xStart;
          (n.recipes || []).forEach((r, ri) => {
            const rKey = key + '/r' + ri;
            const inputNodes = [];
            (r.inputs || []).forEach((x2, xi) => {
              const iKey = rKey + '/i' + xi + ':' + (x2.item_id || x2.name || xi);
              const child = assign(x2, iKey, depth + 1, cursor, visible);
              inputNodes.push(child);
              links.push({ count: x2.count, sx: 0, sy: 0, tx: 0, ty: 0, srcKey: iKey, rKey });
              node.children.push(iKey);
              cursor += subWidth(x2) * SIBLING_X;
            });
            // 配方节点 y：父节点正下方 NODE_H（紧贴），x 取输入中点
            // 这样 配方↔父 距离 = 80（=卡片高），配方↔子 距离 = LEVEL_Y-80 = 96 ≥ 80，均不重叠
            const xs = inputNodes.map(c => c.x);
            const midX = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : x;
            nodes.push({
              key: rKey, node: r, x: midX, y: depth * LEVEL_Y + NODE_H,
              depth: depth + 0.5, visible, hasChildren: true, children: [], isRecipe: true,
            });
            links.push({ count: null, sx: 0, sy: 0, tx: 0, ty: 0, srcKey: key, rKey });
          });
        }
        return node;
      }

      assign(root, 'root', 0, 0, true);

      const byKey = {};
      nodes.forEach(n => { byKey[n.key] = n; });
      links.forEach(l => {
        const s = byKey[l.srcKey], t = byKey[l.rKey];
        if (s && t) {
          l.sx = s.x; l.sy = s.y + NODE_H / 2;
          l.tx = t.x; l.ty = t.y - NODE_H / 2;
        }
      });

      const maxX = Math.max(...nodes.map(n => n.x));
      const maxY = Math.max(...nodes.map(n => n.y));
      return { nodes, links, width: maxX + NODE_W, height: maxY + 100 };
    },

    // ===== 渲染（带视口变换） =====
    _render() {
      const tree = this.data.tree;
      if (!tree) return;
      const query = wx.createSelectorQuery().in(this);
      query.select('#tree-canvas').fields({ node: true, size: true }).exec((res) => {
        if (!res || !res[0] || !res[0].node) return;
        const canvas = res[0].node;
        this._canvas = canvas;
        const ctx = canvas.getContext('2d');
        this._ctx = ctx;

        // 布局（逻辑尺寸）
        const layout = this._layout(tree);
        this._layoutCache = layout;
        this._treeW = layout.width;
        this._treeH = layout.height;

        // 容器宽度 = 屏宽；高度自适应树长（上限 70vh，超过内部滚动手势平移）
        const sys = wx.getSystemInfoSync();
        const cw = sys.windowWidth - 24;   // 页面左右 padding 12*2
        let ch = Math.min(sys.windowHeight * 0.7, layout.height + 60);
        ch = Math.max(240, ch);            // 最小高度
        this._viewW = cw;
        this._viewH = ch;
        this.setData({ canvasW: cw, canvasH: ch, frameH: ch });

        // 初始缩放：适配宽度（树宽超出容器时缩小到框内）
        if (!this._initialized) {
          const fitScale = Math.min(1, cw / layout.width);
          this._view = { scale: fitScale, ox: 0, oy: 0 };
          this._initialized = true;
        }

        // canvas 像素 = 容器 * dpr
        const dpr = sys.pixelRatio || 2;
        canvas.width = cw * dpr;
        canvas.height = ch * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        this._paint(ctx, cw, ch);
        this._preloadCovers();
      });
    },

    // 用当前视口变换绘制整棵树
    _paint(ctx, cw, ch) {
      const layout = this._layoutCache;
      const v = this._view;
      ctx.clearRect(0, 0, cw, ch);

      // 背景网格
      ctx.fillStyle = '#f7f6f1';
      ctx.fillRect(0, 0, cw, ch);

      ctx.save();
      ctx.translate(v.ox + cw / 2, v.oy + 40);
      ctx.scale(v.scale, v.scale);
      // 树根居中于视口顶部（ox 负责水平平移）
      ctx.translate(-layout.width / 2, 0);

      this._drawLinks(ctx, layout.links);
      this._drawNodes(ctx, layout.nodes);
      ctx.restore();
    },

    _drawLinks(ctx, links) {
      ctx.strokeStyle = '#a8aba3';
      ctx.lineWidth = 1.2;
      links.forEach(l => {
        ctx.beginPath();
        ctx.moveTo(l.sx, l.sy);
        ctx.bezierCurveTo(l.sx, (l.sy + l.ty) / 2, l.tx, (l.sy + l.ty) / 2, l.tx, l.ty);
        ctx.stroke();
        if (l.count) {
          ctx.fillStyle = '#665b0b';
          ctx.font = '10px monospace';
          ctx.textAlign = 'center';
          ctx.fillText('×' + l.count, (l.sx + l.tx) / 2, (l.sy + l.ty) / 2 - 4);
        }
      });
    },

    _drawNodes(ctx, nodes) {
      const halfH = NODE_H / 2;
      nodes.forEach(n => {
        const x = n.x, y = n.y;
        const isMachine = n.isRecipe;
        const w = isMachine ? NODE_W + 12 : NODE_W;
        const hw = w / 2;
        // 斜切卡片
        ctx.beginPath();
        ctx.moveTo(x - hw, y - halfH);
        ctx.lineTo(x + hw - 10, y - halfH);
        ctx.lineTo(x + hw, y - halfH + 12);
        ctx.lineTo(x + hw, y + halfH);
        ctx.lineTo(x - hw + 10, y + halfH);
        ctx.lineTo(x - hw, y + halfH - 12);
        ctx.closePath();
        ctx.fillStyle = '#ffffff';
        ctx.strokeStyle = '#242822';
        ctx.lineWidth = 1.2;
        ctx.fill();
        ctx.stroke();

        // 封面图
        const url = n.node.cover;
        const cache = url && this._imgCache[url];
        if (cache && cache.ready) {
          ctx.save();
          ctx.beginPath();
          ctx.rect(x - hw + 6, y - halfH + 8, w - 12, 40);
          ctx.clip();
          ctx.drawImage(cache.image, x - hw + 6, y - halfH + 8, w - 12, 40);
          ctx.restore();
        } else if (url) {
          // 有封面 URL 但加载中：名称首字占位（避免空白）
          this._drawFallback(ctx, x, y, (n.node.name || '?').slice(0, 1));
        } else {
          // 无封面：物品显示名称首字，设备显示 ⚙（不显示无意义的 ITEM/MACHINE）
          this._drawFallback(ctx, x, y, isMachine ? '⚙' : (n.node.name || '?').slice(0, 1));
        }

        ctx.fillStyle = '#20231f';
        ctx.font = '750 10px sans-serif';
        ctx.textAlign = 'center';
        const name = n.node.name || '';
        ctx.fillText(name.length > 7 ? name.slice(0, 7) + '…' : name, x, y + halfH - 12);

        ctx.fillStyle = '#777b73';
        ctx.font = '600 7px monospace';
        ctx.fillText(isMachine ? (n.node.duration || 0) + 's 设备' : (n.node.leaf ? '基础资源' : '物品'), x, y + halfH - 2);

        if (n.hasChildren) {
          ctx.fillStyle = '#191c18';
          ctx.font = '700 12px sans-serif';
          ctx.fillText(this._collapsed.has(n.key) ? '+' : '−', x + hw - 10, y - halfH + 12);
        }
      });
    },

    // 无封面占位：名称首字（大号）或设备 ⚙
    _drawFallback(ctx, x, y, ch) {
      ctx.fillStyle = '#e9e7de';
      ctx.fillRect(x - 34, y - 32, 68, 46);
      ctx.fillStyle = '#8a8f86';
      ctx.font = '800 20px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(ch, x, y - 6);
      ctx.textBaseline = 'alphabetic';
    },

    _preloadCovers() {      const nodes = this._layoutCache.nodes;
      nodes.forEach(n => {
        const url = n.node.cover;
        if (!url || this._imgCache[url]) return;
        const img = this._canvas.createImage();
        this._imgCache[url] = { ready: false, image: img };
        img.onload = () => {
          this._imgCache[url].ready = true;
          this._repaint();
        };
        img.onerror = () => { this._imgCache[url].ready = false; };
        img.src = this._proxy(url);
      });
    },

    _repaint() {
      if (this._ctx && this._viewW && this._viewH) {
        this._paint(this._ctx, this._viewW, this._viewH);
      }
    },

    _proxy(url) {
      const u = String(url || '');
      if (u.startsWith('https://bbs.hycdn.cn/image/')) {
        const app = getApp();
        return app.globalData.apiBase + '/api/media?url=' + encodeURIComponent(u);
      }
      return u;
    },

    // ===== 交互：拖动 + 缩放 =====
    _onTouchStart(e) {
      const touches = e.touches || [];
      if (touches.length >= 2) {
        // 双指：进入缩放模式
        const t1 = touches[0], t2 = touches[1];
        this._pinch = {
          dist: this._dist(t1, t2),
          scale: this._view.scale,
          cx: (t1.clientX + t2.clientX) / 2,
          cy: (t1.clientY + t2.clientY) / 2,
        };
        this._drag = null;
      } else if (touches.length === 1) {
        this._drag = { x: touches[0].clientX, y: touches[0].clientY, moved: false };
        this._pinch = null;
      }
    },

    _onTouchMove(e) {
      const touches = e.touches || [];
      if (this._pinch && touches.length >= 2) {
        const t1 = touches[0], t2 = touches[1];
        const dist = this._dist(t1, t2);
        if (this._pinch.dist > 0) {
          let ns = this._pinch.scale * (dist / this._pinch.dist);
          ns = Math.max(MIN_SCALE, Math.min(MAX_SCALE, ns));
          this._view.scale = ns;
          this._repaint();
        }
      } else if (this._drag && touches.length === 1) {
        const dx = touches[0].clientX - this._drag.x;
        const dy = touches[0].clientY - this._drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) this._drag.moved = true;
        this._view.ox += dx;
        this._view.oy += dy;
        this._drag.x = touches[0].clientX;
        this._drag.y = touches[0].clientY;
        this._repaint();
      }
    },

    _onTouchEnd(e) {
      // 判断是否点击（无移动）→ 命中节点
      const wasDrag = this._drag && this._drag.moved;
      const touches = e.changedTouches || [];
      this._drag = null;
      this._pinch = null;
      if (!wasDrag && touches.length === 1) {
        this._hitTest(touches[0].clientX, touches[0].clientY);
      }
    },

    _dist(t1, t2) {
      return Math.sqrt(Math.pow(t1.clientX - t2.clientX, 2) + Math.pow(t1.clientY - t2.clientY, 2));
    },

    // 屏幕坐标 → 树坐标 → 命中节点
    _hitTest(clientX, clientY) {
      if (!this._layoutCache) return;
      const query = wx.createSelectorQuery().in(this);
      query.select('#tree-canvas').boundingClientRect((rect) => {
        const px = clientX - rect.left;
        const py = clientY - rect.top;
        const v = this._view;
        // 逆变换回树坐标
        const treeX = (px - v.ox - this._viewW / 2) / v.scale + this._layoutCache.width / 2;
        const treeY = (py - v.oy - 40) / v.scale;
        const halfH = NODE_H / 2;
        const nodes = this._layoutCache.nodes;
        for (let i = nodes.length - 1; i >= 0; i--) {
          const n = nodes[i];
          const w = (n.isRecipe ? NODE_W + 12 : NODE_W) / 2 + 8;
          if (Math.abs(treeX - n.x) <= w && Math.abs(treeY - n.y) <= halfH + 10) {
            this._onNodeTap(n);
            return;
          }
        }
      }).exec();
    },

    _onNodeTap(n) {
      if (n.hasChildren) {
        if (this._collapsed.has(n.key)) this._collapsed.delete(n.key);
        else this._collapsed.add(n.key);
        this._render();
      } else if (n.node && n.node.name) {
        this.triggerEvent('search', { name: n.node.name });
      }
    },

    // 外部控制
    collapseAll() {
      this._collapsed.add('root');
      this._render();
    },
    expandAll() {
      this._collapsed.clear();
      this._render();
    },
  },
});
