import { defineConfig } from 'vitepress'
import path from 'node:path'

const repository = 'https://github.com/hxyulin/rm-map-tools'

const en = {
  nav: [{ text: 'Guides', link: '/getting-started' }, { text: 'Model viewer', link: '/viewer' }],
  sidebar: [
    { text: 'Use the tools', items: [
      { text: 'Overview', link: '/' }, { text: 'Downloads', link: '/releases' }, { text: 'Getting started', link: '/getting-started' },
      { text: 'Exporting', link: '/exporting' }, { text: 'Simplification', link: '/simplification' },
      { text: 'Model viewer', link: '/viewer' }
    ] },
    { text: 'Understand the pipeline', items: [
      { text: 'Architecture', link: '/architecture' }, { text: 'Export presets', link: '/export-presets' },
      { text: 'Simplification counts', link: '/simplification-results' },
      { text: 'Mesh simplification', link: '/mesh-simplification' }, { text: 'Texture atlases', link: '/texture-atlas' },
      { text: 'Composition', link: '/composition' }, { text: 'Semantic bindings', link: '/semantic-export' },
      { text: 'Articulated formats', link: '/articulated-formats' }, { text: 'Performance', link: '/performance' }
    ] },
    { text: 'Contribute', items: [{ text: 'Documentation site', link: '/site' }, { text: 'All references', link: '/' }] }
  ]
}

// Only the pages with a zh/ twin are listed here; deeper technical
// references stay English-only and are reachable from "All references".
const zh = {
  nav: [{ text: '指南', link: '/zh/getting-started' }, { text: '模型查看器', link: '/zh/viewer' }],
  sidebar: [
    { text: '使用工具', items: [
      { text: '总览', link: '/zh/' }, { text: '发布与下载', link: '/zh/releases' }, { text: '入门', link: '/zh/getting-started' },
      { text: '导出', link: '/zh/exporting' }, { text: '简化', link: '/zh/simplification' },
      { text: '模型查看器', link: '/zh/viewer' }
    ] },
    { text: '理解流水线', items: [
      { text: '架构', link: '/zh/architecture' }, { text: '关节设备格式', link: '/zh/articulated-formats' },
      { text: '速度与内存', link: '/zh/performance' }
    ] },
    { text: '参与贡献', items: [{ text: '文档网站', link: '/zh/site' }, { text: '全部参考（英文）', link: '/' }] }
  ]
}

export default defineConfig({
  title: 'rm-map-tools',
  description: 'RoboMaster CAD processing, exports, and interactive model inspection.',
  base: '/rm-map-tools/',
  rewrites: { 'README.md': 'index.md' },
  srcExclude: ['previews/clean/**'],
  locales: {
    // No `label` on purpose: it is what renders the default locale flyout,
    // which links every page to its /zh/ twin whether or not one exists.
    // The navbar language switch is the theme's LangSwitch component, which
    // falls back to the zh homepage when a page has no twin.
    root: { lang: 'en', themeConfig: en },
    zh: { lang: 'zh-CN', themeConfig: zh }
  },
  themeConfig: {
    search: { provider: 'local' },
    socialLinks: [{ icon: 'github', link: repository }],
    editLink: { pattern: `${repository}/edit/main/docs/:path` },
    footer: { message: 'Code and documentation: MIT / Apache-2.0. CAD geometry: DJI / RoboMaster.' }
  },
  markdown: {
    config(md) {
      const fence = md.renderer.rules.fence
      md.renderer.rules.fence = (tokens, i, options, env, self) => tokens[i].info.trim() === 'mermaid'
        ? `<MermaidDiagram source="${encodeURIComponent(tokens[i].content)}" />`
        : fence(tokens, i, options, env, self)
      // Keep repository-relative links useful on GitHub and on the built site.
      const original = md.renderer.rules.link_open || ((tokens, i, options, env, self) => self.renderToken(tokens, i, options))
      md.renderer.rules.link_open = (tokens, i, options, env, self) => {
        const token = tokens[i]
        const href = token.attrGet('href')
        if (href && !/^(?:[a-z]+:|\/|#)/i.test(href)) {
          const source = env.relativePath || 'README.md'
          const [file, anchor] = href.split('#')
          const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(source), file))
          if (resolved.startsWith('../')) {
            token.attrSet('href', `${repository}/blob/main/${resolved.slice(3)}${anchor ? '#' + anchor : ''}`)
          } else if (/\.(?:json|py|rs|toml|yaml|yml|html)$/.test(resolved)) {
            token.attrSet('href', `${repository}/blob/main/docs/${resolved}${anchor ? '#' + anchor : ''}`)
          } else if (resolved === 'README.md') {
            token.attrSet('href', '/index.html' + (anchor ? '#' + anchor : ''))
          }
        }
        return original(tokens, i, options, env, self)
      }
    }
  }
})
