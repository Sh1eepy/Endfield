// utils/api.js — 后端 API 封装（对齐 scripts/api_server.py）
// 所有请求走 wx.request；开发期 urlCheck=false 允许 http://127.0.0.1

const app = getApp();

function request(path, data = {}, method = 'GET') {
  return new Promise((resolve, reject) => {
    wx.request({
      url: app.globalData.apiBase + path,
      method,
      data,
      timeout: 30000,
      header: { 'Content-Type': 'application/json' },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          const detail = res.data && (res.data.detail || res.data.error);
          reject(new Error(typeof detail === 'string' ? detail : 'HTTP ' + res.statusCode));
        }
      },
      fail: (err) => reject(err),
    });
  });
}

module.exports = {
  /** 健康检查 */
  health: () => request('/api/health'),

  /** 全部名称（前端模糊搜索联想） */
  names: () => request('/api/names'),

  /** 配方合成树 / 设备卡 / 知识库回退 / 歧义候选 */
  synthesis: (item, maxDepth = 10) =>
    request(`/api/synthesis?item=${encodeURIComponent(item)}&max_depth=${maxDepth}`),

  /** RAG 问答（意图识别→路由→检索→可选 LLM 生成） */
  ask: (query, topK = 5, genAnswer = true) =>
    request('/api/ask', { query, top_k: topK, gen_answer: genAnswer }, 'POST'),

  /** 干员详情走 synthesis 的知识库回退分支（item=干员名 → kb.sections_struct） */
  operator: (name) => request(`/api/synthesis?item=${encodeURIComponent(name)}`),

  /** 图片/音频白名单代理（WIKI CDN 跨域绕开） */
  mediaUrl: (url) => app.globalData.apiBase + '/api/media?url=' + encodeURIComponent(url),
};
