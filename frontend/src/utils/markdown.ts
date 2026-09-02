import MarkdownIt from 'markdown-it'

// 全局单例，避免每个组件重复实例化
const md = new MarkdownIt({
  html: false, // 不渲染原始 HTML，防 XSS
  breaks: true, // 换行转 <br>（小红书笔记正文大量换行）
  linkify: true, // 自动识别 URL 为链接
})

export function renderMarkdown(text: string): string {
  if (!text) return ''
  return md.render(text)
}
