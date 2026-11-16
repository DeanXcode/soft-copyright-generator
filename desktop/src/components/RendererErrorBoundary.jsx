import React from "react";

export default class RendererErrorBoundary extends React.Component {
  state = { error: null, generation: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    const report = {
      message: String(error?.message || error || "渲染异常"),
      stack: String(error?.stack || "").slice(0, 4000),
      componentStack: String(info?.componentStack || "").slice(0, 4000)
    };
    try {
      window.softCopyright?.reportRendererError?.(report);
      window.softCopyright?.getGenerationStatus?.().then((generation) => {
        if (generation?.running) this.setState({ generation });
      }).catch(() => {});
    } catch (_error) {
      // The fallback must remain usable even when the Electron bridge is unavailable.
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    const message = String(this.state.error?.message || "页面渲染出现异常").replace(/https?:\/\/\S+/gi, "[模型网关]").slice(0, 240);
    const running = Boolean(this.state.generation?.running);
    return (
      <main style={styles.shell} role="alert">
        <section style={styles.card}>
          <div style={styles.icon}>!</div>
          <p style={styles.eyebrow}>RENDERER RECOVERY</p>
          <h1 style={styles.title}>界面渲染出现异常</h1>
          <p style={styles.message}>
            {running ? "后台生成任务仍在运行，材料不会因为界面异常而停止。" : "后台任务状态已保留，可以安全刷新界面后继续。"}
          </p>
          <p style={styles.detail}>{message}</p>
          <button type="button" style={styles.button} onClick={() => window.location.reload()}>
            刷新界面并恢复状态
          </button>
        </section>
      </main>
    );
  }
}

const styles = {
  shell: {
    minHeight: "100vh",
    display: "grid",
    placeItems: "center",
    padding: 32,
    boxSizing: "border-box",
    background: "linear-gradient(145deg, #f4f7fb 0%, #eef2f7 100%)",
    color: "#172033",
    fontFamily: "Inter, 'Microsoft YaHei', sans-serif"
  },
  card: {
    width: "min(560px, 100%)",
    padding: "42px 46px",
    border: "1px solid #d8e0eb",
    borderRadius: 24,
    background: "rgba(255, 255, 255, 0.96)",
    boxShadow: "0 24px 70px rgba(26, 44, 74, 0.14)"
  },
  icon: {
    width: 38,
    height: 38,
    display: "grid",
    placeItems: "center",
    borderRadius: 12,
    background: "#fee2e2",
    color: "#b91c1c",
    fontSize: 24,
    fontWeight: 800
  },
  eyebrow: { margin: "22px 0 8px", color: "#64748b", fontSize: 12, letterSpacing: "0.16em", fontWeight: 700 },
  title: { margin: 0, fontSize: 28, lineHeight: 1.25 },
  message: { margin: "18px 0 10px", color: "#334155", fontSize: 16, lineHeight: 1.7 },
  detail: { margin: "0 0 28px", color: "#64748b", fontSize: 13, lineHeight: 1.6, wordBreak: "break-word" },
  button: { border: 0, borderRadius: 12, padding: "12px 18px", background: "#172033", color: "#fff", fontSize: 14, fontWeight: 700, cursor: "pointer" }
};
