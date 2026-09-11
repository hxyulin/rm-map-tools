<script setup>
import { onMounted, ref } from 'vue'
const props = defineProps({ source: { type: String, required: true } })
const host = ref(null)
const error = ref('')
onMounted(async () => {
  try {
    const { default: mermaid } = await import('mermaid')
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'neutral' })
    const { svg } = await mermaid.render('diagram-' + crypto.randomUUID(), decodeURIComponent(props.source))
    if (host.value) host.value.innerHTML = svg
  } catch { error.value = 'Diagram could not render. View the source diagram on GitHub.' }
})
</script>
<template><div ref="host" class="diagram" role="img" aria-label="Architecture diagram"></div><p v-if="error">{{ error }}</p></template>
<style scoped>.diagram { overflow-x: auto; margin: 24px 0; padding: 16px; background: white; border-radius: 6px; }</style>
