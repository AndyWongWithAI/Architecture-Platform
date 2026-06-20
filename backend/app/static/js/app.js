/* 架构平台前端 JS(Phase 4)
 *
 * 当前仅用 HTMX 2.x(CDN)处理交互,本文件作为未来扩展预留。
 * 例如:看板拖拽 / 实时通知 / 复杂表单验证。
 *
 * HTMX 已通过 base.html CDN 加载。
 */

console.log("架构平台 Web UI loaded");

// htmx 全局配置(可选)
document.addEventListener("htmx:configRequest", function(evt) {
    // 未来:加 CSRF token 等
});

// htmx 错误处理
document.addEventListener("htmx:responseError", function(evt) {
    console.error("HTMX error:", evt.detail);
    if (evt.detail.xhr && evt.detail.xhr.responseText) {
        console.error("Response:", evt.detail.xhr.responseText);
    }
});