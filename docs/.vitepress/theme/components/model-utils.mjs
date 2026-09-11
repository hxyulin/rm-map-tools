import { Euler, Matrix4, Quaternion, Vector3 } from 'three'

export const demoUrdf = `<?xml version="1.0"?>
<robot name="Joint controls example">
  <link name="base"><visual><geometry><box size="1.1 0.5 0.12"/></geometry><material name="base"><color rgba="0.22 0.28 0.36 1"/></material></visual></link>
  <link name="carriage"><visual><geometry><box size="0.24 0.32 0.16"/></geometry><material name="blue"><color rgba="0.12 0.46 0.78 1"/></material></visual></link>
  <joint name="rail" type="prismatic"><parent link="base"/><child link="carriage"/><origin xyz="0 0 0.14"/><axis xyz="1 0 0"/><limit lower="-0.28" upper="0.28" effort="0" velocity="0"/></joint>
  <link name="arm"><visual><origin xyz="0 0 0.28"/><geometry><box size="0.10 0.10 0.56"/></geometry><material name="orange"><color rgba="0.92 0.40 0.12 1"/></material></visual></link>
  <joint name="hinge" type="revolute"><parent link="carriage"/><child link="arm"/><origin xyz="0 0 0.10"/><axis xyz="0 1 0"/><limit lower="-1.2" upper="1.2" effort="0" velocity="0"/></joint>
</robot>`

export function jointControls(robot) {
  return Object.values(robot.joints).filter(j => ['revolute', 'continuous', 'prismatic'].includes(j.jointType)).map(j => {
    const continuous = j.jointType === 'continuous'
    const min = continuous ? -Math.PI : Number(j.limit.lower)
    const max = continuous ? Math.PI : Number(j.limit.upper)
    if (!Number.isFinite(min) || !Number.isFinite(max) || min > max) throw new Error(`Invalid limits for joint ${j.name}`)
    return { name: j.name, min, max, value: Number(j.jointValue[0] || 0), unit: j.jointType === 'prismatic' ? 'm' : 'rad' }
  })
}

export function resolveLocalFile(request, files, modelPath = '') {
  let wanted = decodeURIComponent(request.replace(/^https?:\/\/[^/]+\//, '').replace(/^file:\/*/, '').replace(/^package:\/\//, ''))
  wanted = wanted.split(/[?#]/)[0].replace(/^\/+/, '')
  const normalize = value => {
    const parts = []
    for (const part of value.split('/')) {
      if (part === '..') parts.pop()
      else if (part && part !== '.') parts.push(part)
    }
    return parts.join('/')
  }
  const entries = [...files].map(f => ({ file: f, path: normalize(f.webkitRelativePath || f.name) }))
  const relative = normalize(modelPath.split('/').slice(0, -1).join('/') + '/' + wanted)
  for (const candidate of [relative, normalize(wanted)]) {
    const exact = entries.filter(e => e.path === candidate)
    if (exact.length === 1) return exact[0].file
  }
  // Exported ROS package prefixes need not match the chosen folder name.
  const pieces = normalize(wanted).split('/')
  while (pieces.length) {
    const suffix = pieces.join('/')
    const matches = entries.filter(e => e.path === suffix || e.path.endsWith('/' + suffix))
    if (matches.length === 1) return matches[0].file
    if (matches.length > 1) throw new Error(`Ambiguous mesh path: ${request}. Select a smaller model folder.`)
    pieces.shift()
  }
  throw new Error(`Missing model resource: ${request}. Open the folder containing the model and all its meshes.`)
}

const children = (node, tag) => Array.from(node.childNodes || []).filter(n => n.nodeType === 1 && (!tag || n.tagName === tag))
const one = (node, tag) => children(node, tag)[0]
const content = (node, tag, fallback = '') => one(node, tag)?.textContent.trim() || fallback
const escape = value => String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
function numbers(text, count, fallback) {
  const result = (text || fallback).trim().split(/\s+/).map(Number)
  if (result.length !== count || !result.every(Number.isFinite)) throw new Error(`Expected ${count} finite coordinates: ${text}`)
  return result
}
function pose(node) {
  if (node && ((node.getAttribute('rotation_format') && node.getAttribute('rotation_format') !== 'euler_rpy') || node.getAttribute('degrees') === 'true')) throw new Error('SDF viewer requires radian roll/pitch/yaw poses.')
  const v = numbers(node?.textContent, 6, '0 0 0 0 0 0')
  return new Matrix4().compose(new Vector3(...v.slice(0, 3)), new Quaternion().setFromEuler(new Euler(v[3], v[4], v[5], 'ZYX')), new Vector3(1, 1, 1))
}
function origin(matrix) {
  const p = new Vector3(), q = new Quaternion(), scale = new Vector3()
  matrix.decompose(p, q, scale)
  const e = new Euler().setFromQuaternion(q, 'ZYX')
  return `<origin xyz="${p.toArray().join(' ')}" rpy="${[e.x, e.y, e.z].join(' ')}"/>`
}
function assertTags(node, allowed) {
  for (const item of children(node)) if (!allowed.includes(item.tagName)) throw new Error(`Unsupported SDF <${item.tagName}> inside <${node.tagName}>. Use a single equipment model from export_articulated.py.`)
}

// Deliberately limited to the exporter contract, not a general SDF frame resolver.
export function sdfToUrdf(xml, Parser = globalThis.DOMParser) {
  const doc = new Parser().parseFromString(xml, 'application/xml')
  if (doc.getElementsByTagName('parsererror').length) throw new Error('Invalid SDF XML.')
  const root = doc.documentElement
  if (root.tagName !== 'sdf') throw new Error('Expected an SDF document.')
  assertTags(root, ['model'])
  const models = children(root, 'model')
  if (models.length !== 1) throw new Error('Select a single equipment model.sdf, not a world.')
  const model = models[0]
  assertTags(model, ['static', 'link', 'joint'])
  const links = new Map()
  for (const link of children(model, 'link')) {
    const name = link.getAttribute('name')
    if (!name || links.has(name)) throw new Error('SDF link names must be unique and nonempty.')
    assertTags(link, ['pose', 'kinematic', 'gravity', 'visual', 'collision'])
    const p = one(link, 'pose')
    const relative = p?.getAttribute('relative_to')
    if (relative && relative !== '__model__') throw new Error('SDF link poses must be relative to __model__.')
    links.set(name, { node: link, matrix: pose(p) })
  }
  if (!links.size) throw new Error('The SDF model contains no links.')
  const joints = [], childLinks = new Set()
  for (const joint of children(model, 'joint')) {
    assertTags(joint, ['parent', 'child', 'pose', 'axis'])
    const type = joint.getAttribute('type'), parent = content(joint, 'parent'), child = content(joint, 'child')
    if (!['fixed', 'revolute', 'prismatic'].includes(type)) throw new Error(`Unsupported SDF joint type: ${type}`)
    if (!links.has(parent) || !links.has(child) || childLinks.has(child) || parent === child) throw new Error('SDF joints must form a link tree.')
    childLinks.add(child)
    const p = one(joint, 'pose')
    const relative = p?.getAttribute('relative_to')
    if (relative && relative !== child) throw new Error('SDF joint frames must be relative to their child link.')
    if (!pose(p).equals(new Matrix4())) throw new Error('SDF viewer requires the joint frame to coincide with its child link.')
    const axis = one(joint, 'axis')
    if (axis) assertTags(axis, ['xyz', 'limit'])
    const xyz = one(axis || {}, 'xyz')
    if (xyz?.getAttribute('expressed_in')) throw new Error('SDF axes must use the joint frame.')
    const limit = one(axis || {}, 'limit')
    const lo = content(limit || {}, 'lower'), hi = content(limit || {}, 'upper')
    if (type === 'prismatic' && (!lo || !hi)) throw new Error('Sliding joints require finite travel limits.')
    if ((lo || hi) && (!lo || !hi || !Number.isFinite(Number(lo)) || !Number.isFinite(Number(hi)) || Number(lo) > Number(hi))) throw new Error('Invalid SDF joint limits.')
    const urdfType = type === 'revolute' && !lo && !hi ? 'continuous' : type
    const m = links.get(parent).matrix.clone().invert().multiply(links.get(child).matrix)
    joints.push({ parent, child, xml: `<joint name="${escape(joint.getAttribute('name'))}" type="${urdfType}"><parent link="${escape(parent)}"/><child link="${escape(child)}"/>${origin(m)}${type === 'fixed' ? '' : `<axis xyz="${numbers(xyz?.textContent, 3, '0 0 1').join(' ')}"/>${lo && hi ? `<limit lower="${escape(lo)}" upper="${escape(hi)}" effort="0" velocity="0"/>` : ''}`}</joint>` })
  }
  const roots = [...links.keys()].filter(name => !childLinks.has(name))
  if (roots.length !== 1) throw new Error('SDF equipment must have one root link.')
  const visited = new Set()
  const visit = name => { if (visited.has(name)) throw new Error('SDF joint cycle.'); visited.add(name); joints.filter(j => j.parent === name).forEach(j => visit(j.child)) }
  visit(roots[0])
  if (visited.size !== links.size) throw new Error('SDF contains disconnected links or a joint cycle.')
  const output = [`<robot name="${escape(model.getAttribute('name') || 'equipment')}">`]
  // An explicit root anchor preserves nonidentity root poses in SDF model coordinates.
  let anchor = '__sdf_model__'
  while (links.has(anchor)) anchor += '_'
  output.push(`<link name="${anchor}"/><joint name="${anchor}_root" type="fixed"><parent link="${anchor}"/><child link="${escape(roots[0])}"/>${origin(links.get(roots[0]).matrix)}</joint>`)
  for (const [name, { node }] of links) {
    output.push(`<link name="${escape(name)}">`)
    for (const visual of children(node, 'visual')) {
      assertTags(visual, ['pose', 'geometry', 'material'])
      const vp = one(visual, 'pose')
      if (vp?.getAttribute('relative_to') && vp.getAttribute('relative_to') !== name) throw new Error('SDF visual poses must be link-local.')
      const geometry = one(visual, 'geometry')
      if (!geometry) throw new Error('Missing SDF visual geometry.')
      assertTags(geometry, ['mesh'])
      const mesh = one(geometry, 'mesh')
      if (!mesh) throw new Error('SDF equipment viewer requires mesh geometry.')
      assertTags(mesh, ['uri', 'scale'])
      const uri = content(mesh, 'uri')
      if (!uri) throw new Error('Missing SDF mesh URI.')
      const color = numbers(content(one(visual, 'material') || {}, 'diffuse'), 4, '0.65 0.68 0.72 1')
      output.push(`<visual>${origin(pose(vp))}<geometry><mesh filename="${escape(uri)}" scale="${numbers(content(mesh, 'scale'), 3, '1 1 1').join(' ')}"/></geometry><material name=""><color rgba="${color.join(' ')}"/></material></visual>`)
    }
    output.push('</link>')
  }
  return [...output, ...joints.map(j => j.xml), '</robot>'].join('')
}

export function bindCatalogJoints(gltf, model) {
  const nodes = new Map()
  gltf.scene.traverse(node => {
    const index = gltf.parser.associations.get(node)?.nodes
    if (index !== undefined) nodes.set(index, node)
  })
  const bindings = new Map()
  const controls = model.joints.map(joint => {
    const node = nodes.get(joint.motion_node)
    if (!node) throw new Error(`Missing motion node for ${joint.id}`)
    const axis = new Vector3(...joint.axis)
    if (Math.abs(axis.length() - 1) > 1e-6) throw new Error(`Invalid axis for ${joint.id}`)
    const [min, max] = joint.limits
    if (![min, max].every(Number.isFinite) || min > 0 || max < 0) throw new Error(`Invalid travel for ${joint.id}`)
    let meshes = 0
    node.traverse(child => { if (child.isMesh) meshes++ })
    if (!meshes) throw new Error(`No moving geometry bound to ${joint.id}`)
    bindings.set(joint.id, { node, axis, min, max, type: joint.type })
    return { name: joint.id, label: joint.label, min, max, value: 0, unit: joint.type === 'prismatic' ? 'm' : 'rad' }
  })
  gltf.scene.setJointValue = (id, value) => {
    const binding = bindings.get(id)
    if (!binding || !Number.isFinite(value)) throw new Error(`Invalid joint coordinate: ${id}`)
    const { node, axis, min, max, type } = binding
    value = Math.max(min, Math.min(max, value))
    node.matrixAutoUpdate = true
    if (type === 'prismatic') node.position.copy(axis).multiplyScalar(value)
    else node.quaternion.setFromAxisAngle(axis, value)
    node.updateMatrix()
  }
  return { controls, nodes: new Map([...bindings].map(([id, b]) => [id, b.node])) }
}

export async function readCatalogModel(response) {
  const buffer = await response.arrayBuffer()
  const header = new Uint8Array(buffer, 0, Math.min(2, buffer.byteLength))
  // Some static hosts send Content-Encoding: gzip, which fetch decodes itself.
  if (header[0] !== 0x1f || header[1] !== 0x8b) return buffer
  return new Response(new Blob([buffer]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer()
}
