import DefaultTheme from 'vitepress/theme'
import ModelViewer from './components/ModelViewer.vue'
import MermaidDiagram from './components/MermaidDiagram.vue'
import LangSwitch from './components/LangSwitch.vue'
import Layout from './Layout.vue'
import './style.css'
export default {
  extends: DefaultTheme,
  Layout,
  enhanceApp({ app }) {
    app.component('ModelViewer', ModelViewer)
    app.component('MermaidDiagram', MermaidDiagram)
    app.component('LangSwitch', LangSwitch)
  }
}
