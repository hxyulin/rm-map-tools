import { defineConfig } from 'vitepress'
import path from 'node:path'

const repository = 'https://github.com/hxyulin/rm-map-tools'
export default defineConfig({
  title: 'rm-map-tools',
  description: 'RoboMaster CAD processing, exports, and interactive model inspection.',
  base: '/rm-map-tools/',
  rewrites: { 'README.md': 'index.md' },
  srcExclude: ['previews/clean/**'],
  themeConfig: {
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
    ],
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
