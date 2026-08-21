// app.js — 全局逻辑
// 视觉 token 与 API 基址在此集中管理。
// 开发期默认连本地 127.0.0.1:8000；真机预览需改成电脑局域网 IP 或线上 https 域名，
// 并在开发者工具勾选"不校验合法域名"。

App({
  globalData: {
    apiBase: 'http://127.0.0.1:8000',
    // 配方/问答双模式的独立查询记忆（对齐网页端行为）
    synQuery: '',
    askQuery: '',
  },
  onLaunch() {
    // 启动时预热后端状态（不阻塞页面）
    wx.request({
      url: this.globalData.apiBase + '/api/health',
      method: 'GET',
      timeout: 5000,
      success: (res) => {
        this.globalData.backendOk = !!(res.data && res.data.status === 'ok');
      },
      fail: () => { this.globalData.backendOk = false; },
    });
  },
});
