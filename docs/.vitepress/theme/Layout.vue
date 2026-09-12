<script setup>
import DefaultTheme from 'vitepress/theme'
import LangSwitch from './components/LangSwitch.vue'

const { Layout } = DefaultTheme
</script>

<template>
  <Layout>
    <template #nav-bar-content-after>
      <LangSwitch class="nav" />
    </template>
    <template #nav-screen-content-after>
      <LangSwitch class="screen" />
    </template>
  </Layout>
</template>
