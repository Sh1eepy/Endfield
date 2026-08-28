// utils/markdown.js — 轻量 markdown → rich-text nodes 解析器
// 用途：小程序知识问答答案渲染（避免把 **、*、- 等 markdown 原始符号直接暴露给用户）
// 规则对齐网页端 AskResult 的 mdToNodes，额外支持标题 / 引用 / 分隔线 / 代码块 / 表格。
// 安全：只生成受控节点（text / 白名单标签），不注入 HTML 字符串，无 XSS 风险。
// 无 wx 依赖，可在 Node 环境直接 require 做单元测试。

// ---- 块级节点基础样式（rich-text 内部节点只能靠 attrs.style 控制） ----
var BASE_STYLE = {
  p: 'margin:6px 0; line-height:1.75',
  h1: 'margin:12px 0 6px; font-size:20px; font-weight:600; line-height:1.5',
  h2: 'margin:12px 0 6px; font-size:18px; font-weight:600; line-height:1.5',
  h3: 'margin:10px 0 6px; font-size:16px; font-weight:600; line-height:1.5',
  h4: 'margin:10px 0 6px; font-size:15px; font-weight:600; line-height:1.5',
  h5: 'margin:8px 0 4px; font-size:14px; font-weight:600; line-height:1.5',
  h6: 'margin:8px 0 4px; font-size:14px; font-weight:600; line-height:1.5',
  ul: 'margin:6px 0; padding-left:18px',
  li: 'margin:3px 0; line-height:1.7',
  blockquote: 'margin:6px 0; padding:2px 10px; border-left:3px solid #cfd4e0; color:#5a6478; line-height:1.7',
  code: 'font-family:monospace; background:#f0f1f4; padding:0 3px; border-radius:3px',
  hr: 'margin:10px 0; border:none; border-top:1px solid #e0e0e0',
  div: 'font-family:monospace; background:#f6f6f8; padding:8px 10px; margin:8px 0; border-radius:6px; line-height:1.6',
};

// 内联 token 正则：**加粗**、`代码`、*斜体*（与网页端 AskResult 一致，* 不能跨行）
var INLINE_RE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*)/g;

/** 构建一个标签节点 */
function node(name, children, extraStyle) {
  var attrs = {};
  var style = BASE_STYLE[name] || '';
  if (extraStyle) style = style ? style + '; ' + extraStyle : extraStyle;
  if (style) attrs.style = style;
  return { name: name, type: 'node', attrs: attrs, children: children };
}

/** 纯文本节点 */
function text(t) {
  return { type: 'text', text: t };
}

/** 内联解析：**加粗**、*斜体*、`代码` → [text, strong, em, code...] */
function inlineToNodes(raw) {
  var children = [];
  var last = 0;
  var m;
  var re = new RegExp(INLINE_RE.source, 'g');
  while ((m = re.exec(raw)) !== null) {
    if (m.index > last) children.push(text(raw.slice(last, m.index)));
    var tok = m[0];
    if (tok.indexOf('**') === 0) {
      children.push(node('strong', [text(tok.slice(2, -2))]));
    } else if (tok.indexOf('`') === 0) {
      children.push(node('code', [text(tok.slice(1, -1))]));
    } else {
      children.push(node('em', [text(tok.slice(1, -1))]));
    }
    last = m.index + tok.length;
  }
  if (last < raw.length) children.push(text(raw.slice(last)));
  return children.length ? children : [text(raw)];
}

/** 解析代码围栏块：```lang\n...\n```，逐行保留换行（rich-text 内用 br 分隔） */
function parseCodeBlock(lines, i, nodes) {
  i++; // 跳过开头 ```（可能带语言名）
  var code = [];
  while (i < lines.length && !/^```/.test(lines[i].trim())) {
    code.push(lines[i]);
    i++;
  }
  if (i < lines.length) i++; // 跳过结尾 ```
  if (!code.length) return i;
  var children = [];
  code.forEach(function (ln, idx) {
    children.push(text(ln));
    if (idx < code.length - 1) children.push({ name: 'br', type: 'node' });
  });
  nodes.push(node('div', children));
  return i;
}

/** 解析 markdown 表格：连续 | 行，第二行是 --- 分隔行时作为表头 */
function parseTable(lines, i, nodes) {
  var rows = [];
  while (i < lines.length && /^\|.*\|\s*$/.test(lines[i].trim())) {
    var cells = lines[i].trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (c) { return c.trim(); });
    rows.push(cells);
    i++;
  }
  if (!rows.length) return i;
  var header = rows[0] || [];
  var body = rows.slice(1);
  // 去掉 |-|-| 分隔行
  if (body.length && body[0].every(function (c) { return /^:?-{2,}:?$/.test(c); })) {
    body = body.slice(1);
  }
  var trs = [];
  trs.push(node('tr', header.map(function (c) {
    return node('th', inlineToNodes(c), 'border:1px solid #d8d8d8; padding:4px 8px; background:#f5f6fa; font-weight:600; text-align:left');
  })));
  body.forEach(function (row) {
    trs.push(node('tr', row.map(function (c) {
      return node('td', inlineToNodes(c), 'border:1px solid #d8d8d8; padding:4px 8px');
    })));
  });
  nodes.push(node('table', trs, 'width:100%; border-collapse:collapse; margin:8px 0; font-size:13px'));
  return i;
}

/**
 * 整段 markdown → rich-text nodes 数组
 * 支持：标题(#~######)、列表(-、*、•、数字序号)、引用(>)、分隔线(---、***)、
 *       代码块(```)、表格(| a | b |)、段落；内联加粗、斜体、行内代码
 * @param {string} md
 * @returns {Array} rich-text nodes
 */
function mdToNodes(md) {
  var src = String(md == null ? '' : md).replace(/\r\n/g, '\n');
  var lines = src.split('\n');
  var nodes = [];
  var i = 0;
  var n = lines.length;
  while (i < n) {
    var ln = lines[i];
    var t = ln.trim();
    // 空行：跳过
    if (!t) { i++; continue; }
    // 代码围栏
    if (/^```/.test(t)) { i = parseCodeBlock(lines, i, nodes); continue; }
    // 标题
    var h = /^(#{1,6})\s+(.*)$/.exec(t);
    if (h) {
      nodes.push(node('h' + h[1].length, inlineToNodes(h[2])));
      i++;
      continue;
    }
    // 分隔线
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(t)) {
      nodes.push(node('hr', []));
      i++;
      continue;
    }
    // 引用（连续引用行合并）
    if (/^>\s?/.test(t)) {
      var q = [];
      while (i < n && /^>\s?/.test(lines[i].trim())) {
        q.push(lines[i].trim().replace(/^>\s?/, ''));
        i++;
      }
      var qChildren = [];
      q.forEach(function (ql, qi) {
        qChildren = qChildren.concat(inlineToNodes(ql));
        if (qi < q.length - 1) qChildren.push({ name: 'br', type: 'node' });
      });
      nodes.push(node('blockquote', qChildren));
      continue;
    }
    // 列表（- * • 或 数字.），连续项合并
    if (/^([-*•]|\d+[.)])\s+/.test(t)) {
      var items = [];
      while (i < n) {
        var tm = /^([-*•]|\d+[.)])\s+(.*)$/.exec(lines[i].trim());
        if (!tm) break;
        items.push(tm[2]);
        i++;
      }
      nodes.push(node('ul', items.map(function (it) { return node('li', inlineToNodes(it)); })));
      continue;
    }
    // 表格
    if (/^\|.*\|$/.test(t)) { i = parseTable(lines, i, nodes); continue; }
    // 普通段落：连续非空普通行合并成一段（行间 br 保留换行感）
    var para = [];
    while (i < n) {
      var pt = lines[i].trim();
      if (!pt) break;
      // 遇到新的块级标记则停止合并
      if (/^(#{1,6})\s+/.test(pt) || /^(-{3,}|\*{3,}|_{3,})\s*$/.test(pt) ||
          /^>\s?/.test(pt) || /^([-*•]|\d+[.)])\s+/.test(pt) ||
          /^\|.*\|$/.test(pt) || /^```/.test(pt)) break;
      para.push(lines[i]);
      i++;
    }
    var pChildren = [];
    para.forEach(function (pl, pi) {
      pChildren = pChildren.concat(inlineToNodes(pl));
      if (pi < para.length - 1) pChildren.push({ name: 'br', type: 'node' });
    });
    if (pChildren.length) nodes.push(node('p', pChildren));
  }
  return nodes;
}

module.exports = { mdToNodes: mdToNodes };
