// components/entry-curtain/entry-curtain.js — 开场动画（SYSTEM BOOT）
// 对齐网页 v8 staged mechanical boot：logo 板机械锁定 + 进度条到 100% 退场
// 减少动态（prefers-reduced-motion）时直接跳过

Component({
  properties: {
    // 是否显示（页面 onLoad 后由父组件控制）
    show: { type: Boolean, value: true },
  },

  data: {
    percent: 0,
    leaving: false,
    done: false,
  },

  lifetimes: {
    attached() {
      this._timer = null;
      this._checkReducedMotion();
    },
    detached() {
      if (this._timer) clearInterval(this._timer);
    },
  },

  methods: {
    _checkReducedMotion() {
      // 小程序无 prefers-reduced-motion API，用 wx.getSystemInfo 判断（iOS 低功耗模式/部分安卓）
      // 简化：提供 skip 属性由页面决定；这里默认正常播放
      this._start();
    },

    _start() {
      let p = 0;
      // 加长：110ms 步进，整体动画约 4.5-5s
      // 节奏：前段快、中段慢、尾段卡顿（更有"加载感"）
      this._timer = setInterval(() => {
        const step = p < 60 ? Math.floor(Math.random() * 10) + 5   // 前段 5-14
          : p < 88 ? Math.floor(Math.random() * 6) + 2             // 中段 2-7
          : p < 96 ? 2                                             // 尾段慢
          : 1;
        p += step;
        if (p >= 100) {
          p = 100;
          clearInterval(this._timer);
          this.setData({ percent: p });
          // 显示 SYSTEM READY 后多停一会再退场
          setTimeout(() => this._finish(), 850);
        } else {
          this.setData({ percent: p });
        }
      }, 110);
    },

    _finish() {
      this.setData({ leaving: true });
      // 幕布滑出后彻底移除
      setTimeout(() => {
        this.setData({ done: true });
        this.triggerEvent('complete');
      }, 700);
    },

    // 供外部跳过（减少动态/调试）
    skip() {
      if (this._timer) clearInterval(this._timer);
      this.setData({ percent: 100 });
      this._finish();
    },
  },
});
