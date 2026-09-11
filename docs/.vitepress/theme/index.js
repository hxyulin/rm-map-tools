import DefaultTheme from 'vitepress/theme'
import ModelViewer from './components/ModelViewer.vue'
import MermaidDiagram from './components/MermaidDiagram.vue'
import './style.css'
export default {
  extends: DefaultTheme,
  enhanceApp({ app }) { app.component('ModelViewer', ModelViewer); app.component('MermaidDiagram', MermaidDiagram) }
}
