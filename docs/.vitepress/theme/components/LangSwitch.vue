<script setup>
import { computed } from 'vue'
import { useData, withBase } from 'vitepress'

// Pages with a docs/zh/ twin. Keep in sync with the locale sidebars in
// config.mjs; anything else falls back to the Chinese homepage.
const zhTwins = {
  'README.md': '/zh/',
  'getting-started.md': '/zh/getting-started.html',
  'exporting.md': '/zh/exporting.html',
  'simplification.md': '/zh/simplification.html',
  'architecture.md': '/zh/architecture.html',
  'releases.md': '/zh/releases.html',
  'viewer.md': '/zh/viewer.html',
  'site.md': '/zh/site.html',
  'performance.md': '/zh/performance.html',
  'articulated-formats.md': '/zh/articulated-formats.html'
}

const { localeIndex, page } = useData()

const link = computed(() => {
  const path = page.value.relativePath
  if (path.startsWith('zh/')) {
    const rest = path.slice(3)
    return withBase(rest === 'index.md' ? '/' : `/${rest.replace(/\.md$/, '.html')}`)
  }
  return withBase(zhTwins[path] ?? '/zh/')
})
</script>

<template>
  <div class="VPNavLangSwitch">
    <template v-if="localeIndex === 'root'">
      <span class="current">EN</span>
      <a class="other" :href="link" lang="zh-CN" hreflang="zh-CN">简体中文</a>
    </template>
    <template v-else>
      <a class="other" :href="link" lang="en" hreflang="en">English</a>
      <span class="current">简体中文</span>
    </template>
  </div>
</template>

<style scoped>
.VPNavLangSwitch {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  white-space: nowrap;
}

.VPNavLangSwitch.nav {
  padding-left: 16px;
}

.VPNavLangSwitch.screen {
  padding: 0 24px;
  line-height: 48px;
}

.current {
  color: var(--vp-c-text-1);
  font-weight: 600;
}

.other {
  color: var(--vp-c-text-2);
  transition: color 0.25s;
}

.other:hover {
  color: var(--vp-c-brand-1);
}
</style>
