import MarkdownIt from 'markdown-it'

// 全局单例，避免每个组件重复实例化
const md = new MarkdownIt({
  html: false, // 不渲染原始 HTML，防 XSS
  breaks: true, // 换行转 <br>（小红书笔记正文大量换行）
  linkify: true, // 自动识别 URL 为链接
})

// 所有链接在新页面打开，防止离开当前行程页
const defaultLinkRenderer = md.renderer.rules.link_open
  || ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer')
  return defaultLinkRenderer(tokens, idx, options, env, self)
}

export function renderMarkdown(text: string): string {
  if (!text) return ''
  return md.render(text)
}
