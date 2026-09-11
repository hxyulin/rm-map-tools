<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { withBase } from 'vitepress'

const canvasHost = ref(null)
const status = ref('Loading viewer…')
const error = ref('')
const catalog = ref([])
const mechanism = ref('base')
const mechanismNote = ref('')
const models = ref([])
const selected = ref('')
const joints = ref([])
const clips = ref([])
const clipIndex = ref(0)
const timeline = ref(0)
const duration = ref(0)
const playing = ref(false)
const ready = ref(false)
const loading = ref(false)
const coreAvailable = ref(false), draggingTool = ref(false), toolStatus = ref('')
let coreIK, toolTarget, transform
let files = [], api, renderer, scene, camera, orbit, object, mixer, action, observer, raf, active = true, loadId = 0
let urls = []
let jointNodes = new Map(), fetchController
const filePath = f => f.webkitRelativePath || f.name

function disposeObject(target) {
  if (!target) return
  const geometries = new Set(), materials = new Set(), textures = new Set()
  target.traverse(node => {
    if (node.geometry) geometries.add(node.geometry)
    for (const m of Array.isArray(node.material) ? node.material : node.material ? [node.material] : []) materials.add(m)
  })
  for (const m of materials) for (const v of Object.values(m)) if (v?.isTexture) textures.add(v)
  textures.forEach(t => t.dispose()); materials.forEach(m => m.dispose()); geometries.forEach(g => g.dispose())
}
function clearModel() {
  draggingTool.value = false; coreAvailable.value = false; toolStatus.value = ''; coreIK = null
  transform?.detach(); if (orbit) orbit.enabled = true
  if (toolTarget) { scene.remove(toolTarget); toolTarget = null }
  playing.value = false
  if (mixer) { mixer.stopAllAction(); mixer.uncacheRoot(object); mixer = null; action = null }
  if (object) { scene.remove(object); disposeObject(object); object = null }
  urls.forEach(URL.revokeObjectURL); urls = []
  jointNodes.clear(); joints.value = []; clips.value = []; timeline.value = 0; duration.value = 0
}
function fit(target = object) {
  if (!target) return
  object.updateMatrixWorld(true)
  const box = new api.THREE.Box3().setFromObject(target)
  if (box.isEmpty()) return
  const center = box.getCenter(new api.THREE.Vector3()), size = box.getSize(new api.THREE.Vector3()).length() || 1
  orbit.target.copy(center)
  camera.position.copy(center).add(new api.THREE.Vector3(1.2, -1.7, 1.1).normalize().multiplyScalar(size * 1.6))
  camera.near = Math.max(size / 10000, 0.00001); camera.far = size * 100
  camera.updateProjectionMatrix(); orbit.update()
}
function updateJoint(joint, value) {
  if (!object?.setJointValue) return
  joint.value = Math.max(joint.min, Math.min(joint.max, Number(value)))
  object.setJointValue(joint.name, joint.value)
  syncTool()
}
function syncTool() {
  if (coreIK && toolTarget) toolTarget.position.copy(coreIK.position())
  toolStatus.value = ''
}
function toggleTool() {
  draggingTool.value = !draggingTool.value
  syncTool()
  if (draggingTool.value) transform.attach(toolTarget)
  else transform.detach()
}
function chooseClip() {
  if (!mixer) return
  mixer.stopAllAction()
  action = mixer.clipAction(clips.value[Number(clipIndex.value)])
  action.play(); action.paused = true
  duration.value = action.getClip().duration
  timeline.value = 0; scrub(0)
}
function scrub(value) {
  timeline.value = Number(value)
  if (action) { action.time = timeline.value; mixer.update(0) }
}
function reset() {
  playing.value = false
  joints.value.forEach(j => updateJoint(j, 0))
  scrub(0)
}
async function showModel(file) {
  const requestId = ++loadId
  loading.value = true; ready.value = false; error.value = ''; status.value = `Loading ${file.name}…`
  clearModel()
  const pending = []
  let candidate = null
  try {
    const { THREE, URDFLoader, GLTFLoader, STLLoader, ColladaLoader, utils } = api
    if (file?.name.toLowerCase().endsWith('.glb')) {
      const manager = new THREE.LoadingManager()
      manager.setURLModifier(url => {
        if (url.startsWith('blob:') || url.startsWith('data:')) return url
        const resolved = utils.resolveLocalFile(url, files, filePath(file))
        const blob = URL.createObjectURL(resolved); urls.push(blob); return blob
      })
      const gltf = await new GLTFLoader(manager).parseAsync(await file.arrayBuffer(), '')
      candidate = gltf.scene
      // glTF is Y-up; the equipment XML and this view use Z-up.
      candidate.rotation.x = Math.PI / 2
      if (requestId !== loadId || !active) { disposeObject(candidate); return }
      object = candidate; scene.add(object)
      clips.value = gltf.animations; clipIndex.value = 0
      if (clips.value.length) { mixer = new THREE.AnimationMixer(object); chooseClip() }
    } else {
      let xml = await file.text()
      if (file?.name.toLowerCase().endsWith('.sdf')) xml = utils.sdfToUrdf(xml)
      const parsed = new DOMParser().parseFromString(xml, 'application/xml')
      if (parsed.querySelector('parsererror') || parsed.documentElement.tagName !== 'robot') throw new Error('Choose a valid URDF robot or exported equipment SDF.')
      const manager = new THREE.LoadingManager()
      manager.setURLModifier(url => {
        if (url.startsWith('blob:') || url.startsWith('data:')) return url
        const resolved = utils.resolveLocalFile(url, files, file ? filePath(file) : '')
        const blob = URL.createObjectURL(resolved); urls.push(blob); return blob
      })
      const loader = new URDFLoader(manager)
      loader.parseCollision = false
      loader.packages = name => name
      loader.loadMeshCb = (path, manager, material, done) => {
        const task = (async () => {
          const source = utils.resolveLocalFile(path, files, file ? filePath(file) : '')
          const extension = source.name.split('.').pop().toLowerCase()
          let mesh
          if (extension === 'stl') mesh = new THREE.Mesh(new STLLoader().parse(await source.arrayBuffer()), material)
          else if (extension === 'dae') mesh = new ColladaLoader(manager).parse(await source.text(), path.split('/').slice(0, -1).join('/') + '/').scene
          else if (extension === 'glb') mesh = (await new GLTFLoader(manager).parseAsync(await source.arrayBuffer(), '')).scene
          else throw new Error(`Unsupported mesh type: .${extension}. Use STL, DAE, or GLB meshes.`)
          if (requestId !== loadId || !active) { disposeObject(mesh); return }
          done(mesh)
        })()
        pending.push(task)
      }
      candidate = loader.parse(xml)
      await Promise.all(pending)
      if (requestId !== loadId || !active) { disposeObject(candidate); return }
      object = candidate; scene.add(object)
      joints.value = utils.jointControls(object)
    }
    fit(); ready.value = true
    status.value = `${file.name} · ${joints.value.length} adjustable joints`
  } catch (e) {
    // Wait for other mesh reads before disposing partially loaded geometry.
    await Promise.allSettled(pending)
    if (requestId !== loadId || !active) { disposeObject(candidate); return }
    if (candidate !== object) disposeObject(candidate)
    clearModel(); error.value = e.message || String(e); status.value = 'Model could not be loaded'
  } finally { if (requestId === loadId && active) loading.value = false }
}
function openFiles(event) {
  files = Array.from(event.target.files || [])
  models.value = files.filter(f => /\.(urdf|sdf|glb)$/i.test(f.name)).map(f => ({ name: filePath(f), file: f }))
  // Prefer an equipment description over its mesh resources.
  models.value.sort((a, b) => Number(/\.glb$/i.test(a.name)) - Number(/\.glb$/i.test(b.name)) || a.name.localeCompare(b.name))
  selected.value = models.value[0]?.name || ''
  if (!selected.value) { error.value = 'No GLB, URDF, or SDF model was found in that selection.'; return }
  loadSelected()
}
function loadSelected() { const model = models.value.find(m => m.name === selected.value); if (model) showModel(model.file) }
async function browseMechanisms() {
  if (!catalog.value.length) {
    try {
      const response = await fetch(withBase('/models/catalog.json'))
      if (!response.ok) throw new Error('The mechanism catalog is missing from this site build.')
      const data = await response.json()
      if (data.schema_version !== 1 || !data.models?.length) throw new Error('Invalid mechanism catalog.')
      catalog.value = data.models
    } catch (e) { error.value = e.message; status.value = 'Mechanisms unavailable'; return }
  }
  await showMechanism()
}
async function showMechanism() {
  const model = catalog.value.find(item => item.id === mechanism.value)
  if (!model) return
  const requestId = ++loadId
  fetchController?.abort(); fetchController = new AbortController()
  clearModel(); loading.value = true; ready.value = false; error.value = ''
  models.value = []; selected.value = ''; mechanismNote.value = model.note
  status.value = `Loading ${model.label} · ${(model.bytes / 1e6).toFixed(1)} MB…`
  let candidate
  try {
    const response = await fetch(withBase('/models/' + model.file), { signal: fetchController.signal })
    if (!response.ok) throw new Error(`Could not download ${model.label}.`)
    const buffer = await api.utils.readCatalogModel(response)
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buffer)), b => b.toString(16).padStart(2, '0')).join('')
    if (digest !== model.sha256) throw new Error(`The downloaded ${model.label} does not match its catalog checksum.`)
    const gltf = await new api.GLTFLoader().parseAsync(buffer, '')
    candidate = gltf.scene
    if (!active || requestId !== loadId) { disposeObject(candidate); return }
    const binding = api.utils.bindCatalogJoints(gltf, model)
    joints.value = binding.controls; jointNodes = binding.nodes
    if (model.up[1] === 1) candidate.rotation.x = Math.PI / 2
    object = candidate; scene.add(object)
    coreIK = api.createCoreIK(object, model, joints.value, jointNodes)
    coreAvailable.value = !!coreIK
    if (coreIK) { toolTarget = new api.THREE.Object3D(); scene.add(toolTarget); syncTool() }
    fit(); ready.value = true
    status.value = `${model.label} · ${joints.value.length} movable entities`
  } catch (e) {
    if (candidate !== object) disposeObject(candidate)
    if (active && requestId === loadId) { clearModel(); error.value = e.message; status.value = 'Model could not be loaded' }
  } finally { if (active && requestId === loadId) loading.value = false }
}

onMounted(async () => {
  try {
    const [THREE, { OrbitControls }, { default: URDFLoader }, { GLTFLoader }, { STLLoader }, { ColladaLoader }, utils, { TransformControls }, { createCoreIK }] = await Promise.all([
      import('three'), import('three/addons/controls/OrbitControls.js'), import('urdf-loader'),
      import('three/addons/loaders/GLTFLoader.js'), import('three/addons/loaders/STLLoader.js'),
      import('three/addons/loaders/ColladaLoader.js'), import('./model-utils.mjs'),
      import('three/addons/controls/TransformControls.js'), import('./core-ik.mjs')
    ])
    if (!active) return
    api = { THREE, URDFLoader, GLTFLoader, STLLoader, ColladaLoader, utils, createCoreIK }
    scene = new THREE.Scene(); scene.background = new THREE.Color('#101923')
    camera = new THREE.PerspectiveCamera(42, 1, 0.001, 1000); camera.up.set(0, 0, 1)
    renderer = new THREE.WebGLRenderer({ antialias: true }); renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    renderer.domElement.setAttribute('aria-label', 'Interactive 3D model. Use the joint sliders below to change its pose.')
    canvasHost.value.appendChild(renderer.domElement)
    orbit = new OrbitControls(camera, renderer.domElement); orbit.enableDamping = true
    transform = new TransformControls(camera, renderer.domElement)
    transform.setMode('translate'); transform.setSize(0.85)
    scene.add(transform.getHelper())
    transform.addEventListener('dragging-changed', event => { orbit.enabled = !event.value })
    transform.addEventListener('objectChange', () => {
      if (!coreIK || !draggingTool.value) return
      const result = coreIK.solve(toolTarget.position)
      toolStatus.value = `${result.reached ? 'Target reached' : 'Preview range / solver limit'} · ${(result.error * 1000).toFixed(1)} mm remaining`
    })
    scene.add(new THREE.HemisphereLight(0xffffff, 0x526278, 3))
    const light = new THREE.DirectionalLight(0xffffff, 3); light.position.set(3, -4, 6); scene.add(light)
    const grid = new THREE.GridHelper(10, 20, 0x37516a, 0x263747); grid.rotation.x = Math.PI / 2; grid.position.z = -0.065; scene.add(grid)
    observer = new ResizeObserver(() => {
      const { width, height } = canvasHost.value.getBoundingClientRect()
      if (!width || !height) return
      renderer.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix()
    }); observer.observe(canvasHost.value)
    let previous = performance.now()
    const draw = now => {
      if (!active) return
      const delta = Math.min((now - previous) / 1000, 0.1); previous = now
      if (playing.value && duration.value > 0) scrub((timeline.value + delta) % duration.value)
      orbit.update(); renderer.render(scene, camera); raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    await browseMechanisms()
  } catch (e) { status.value = 'Viewer unavailable'; error.value = `WebGL could not start: ${e.message}. Try a browser with hardware acceleration enabled.` }
})
onBeforeUnmount(() => {
  active = false; loadId++; fetchController?.abort(); cancelAnimationFrame(raf); observer?.disconnect(); orbit?.dispose()
  if (scene) { clearModel(); disposeObject(scene) }
  transform?.dispose(); renderer?.dispose(); renderer?.forceContextLoss()
})
</script>

<template>
  <section class="model-viewer" aria-label="Model viewer">
    <div v-if="catalog.length" class="mechanism-picker" aria-label="Choose a mechanism">
      <button v-for="item in catalog" :key="item.id" :aria-pressed="mechanism === item.id && !models.length" :disabled="loading" @click="mechanism = item.id; showMechanism()">{{ item.label }}<span>{{ item.joints.length }} joints</span></button>
    </div>
    <p v-if="mechanismNote && !models.length" class="mechanism-note">{{ mechanismNote }}</p>
    <div class="viewer-toolbar">
      <label class="file-button">Open files<input type="file" multiple accept=".glb,.urdf,.sdf,.stl,.dae,.png,.jpg,.jpeg" :disabled="!api || loading" @change="openFiles" /></label>
      <label class="file-button">Open folder<input type="file" webkitdirectory multiple :disabled="!api || loading" @change="openFiles" /></label>
      <button :disabled="!api || loading" @click="browseMechanisms">Browse mechanisms</button>
      <button :disabled="!ready" @click="fit()">Fit view</button>
      <button :disabled="!ready" @click="reset">Reset</button>
      <button v-if="coreAvailable" :aria-pressed="draggingTool" @click="toggleTool">{{ draggingTool ? 'Stop dragging tool' : 'Drag tool' }}</button>
    </div>
    <label v-if="models.length > 1" class="model-select">Model <select :disabled="loading" v-model="selected" @change="loadSelected"><option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option></select></label>
    <div ref="canvasHost" class="viewer-canvas"></div>
    <p class="viewer-status" role="status">{{ status }}</p>
    <p v-if="draggingTool" class="mechanism-note">Drag an arrow or plane square to move the tool. Orientation is free; joint ranges are preview guards. Use sliders for individual axes.</p>
    <p v-if="toolStatus" class="mechanism-note" role="status">{{ toolStatus }}</p>
    <p v-if="error" class="viewer-error" role="alert">{{ error }}</p>
    <div v-if="joints.length" class="joint-controls">
      <label v-for="j in joints" :key="j.name" class="joint-control">
        <span>{{ j.label || j.name }}</span><output>{{ j.value.toFixed(3) }} {{ j.unit }}</output>
        <input type="range" :aria-label="j.name" :min="j.min" :max="j.max" :step="(j.max - j.min) / 1000 || 0.001" :value="j.value" @input="updateJoint(j, $event.target.value)" />
        <button v-if="jointNodes.has(j.name)" type="button" @click.prevent="fit(jointNodes.get(j.name))">Focus</button>
        <span class="joint-limits">{{ j.min.toFixed(3) }} to {{ j.max.toFixed(3) }} {{ j.unit }}</span>
      </label>
    </div>
    <div v-if="clips.length" class="animation-controls">
      <label>Animation <select v-model="clipIndex" @change="chooseClip"><option v-for="(clip, i) in clips" :key="i" :value="i">{{ clip.name || `Clip ${i + 1}` }}</option></select></label>
      <button @click="playing = !playing">{{ playing ? 'Pause' : 'Play' }}</button>
      <label>Time {{ timeline.toFixed(2) }} / {{ duration.toFixed(2) }} s<input type="range" min="0" :max="duration" step="0.01" :value="timeline" @input="playing = false; scrub($event.target.value)" /></label>
    </div>
  </section>
</template>

<style scoped>
.model-viewer { margin: 24px 0; border: 1px solid var(--vp-c-divider); border-radius: 10px; overflow: hidden; background: var(--vp-c-bg-soft); }
.mechanism-picker { display: flex; flex-wrap: wrap; gap: 8px; padding: 16px 12px 4px; }
.mechanism-picker button { flex: 1 1 130px; text-align: left; }
.mechanism-picker button[aria-pressed=true] { border-color: var(--vp-c-brand-1); box-shadow: inset 0 0 0 1px var(--vp-c-brand-1); }
.mechanism-picker span { display: block; color: var(--vp-c-text-2); font-size: 13px; }
.mechanism-note { padding: 0 16px; font-size: 14px; }
.viewer-toolbar { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px; }
button, .file-button, select { border: 1px solid var(--vp-c-divider); border-radius: 5px; padding: 7px 11px; color: var(--vp-c-text-1); background: var(--vp-c-bg); font: inherit; font-size: 14px; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
button:focus-visible, .file-button:focus-within, select:focus-visible { outline: 2px solid var(--vp-c-brand-1); outline-offset: 2px; }
.file-button { position: relative; }
.file-button input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.viewer-canvas { height: 440px; width: 100%; touch-action: none; }
.viewer-canvas :deep(canvas) { display: block; }
.viewer-status { margin: 0 !important; padding: 10px 16px; font-size: 14px; border-bottom: 1px solid var(--vp-c-divider); }
.viewer-error { padding: 4px 16px; color: var(--vp-c-danger-1); }
.joint-controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; padding: 16px; }
.joint-control { display: grid; grid-template-columns: 1fr auto; gap: 5px 12px; font-size: 14px; }
.joint-control > span:first-child { overflow-wrap: anywhere; }
input[type=range] { width: 100%; grid-column: 1 / -1; accent-color: var(--vp-c-brand-1); min-height: 28px; }
.joint-limits { grid-column: 1 / -1; color: var(--vp-c-text-2); }
output { font-variant-numeric: tabular-nums; }
.animation-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 16px; }
.animation-controls label:last-child { width: 100%; }
.model-select { display: flex; align-items: center; gap: 12px; padding: 0 12px 12px; }
.model-select select { min-width: 0; width: 100%; }
@media(max-width: 600px) { .viewer-canvas { height: 330px; } }
</style>
