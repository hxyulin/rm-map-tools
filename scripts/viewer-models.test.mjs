import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { gunzipSync } from 'node:zlib'
import { createHash } from 'node:crypto'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { Vector3 } from 'three'
import { bindCatalogJoints } from '../docs/.vitepress/theme/components/model-utils.mjs'

const root = process.env.VIEWER_MODELS_DIR
  ? pathToFileURL(path.resolve(process.env.VIEWER_MODELS_DIR) + path.sep)
  : new URL('../docs/public/models/', import.meta.url)
const catalog = JSON.parse(fs.readFileSync(new URL('catalog.json', root)))
assert.deepEqual(catalog.models.map(m => m.id), ['base', 'rune', 'outpost', 'dart-station', 'tech-core'])
for (const model of catalog.models) test(`${model.label}: every control moves bound CAD geometry and resets`, async () => {
  const data = gunzipSync(fs.readFileSync(new URL(model.file, root)))
  assert.equal(createHash('sha256').update(data).digest('hex'), model.sha256)
  const gltf = await new GLTFLoader().parseAsync(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength), '')
  const { controls, nodes } = bindCatalogJoints(gltf, model)
  assert.equal(controls.length, model.joints.length)
  for (const control of controls) {
    gltf.scene.updateMatrixWorld(true)
    const node = nodes.get(control.name), samples = []
    node.traverse(child => {
      const positions = child.geometry?.attributes.position
      if (positions) for (let i = 0; i < positions.count; i += Math.max(1, Math.floor(positions.count / 8))) {
        samples.push({ mesh: child, local: new Vector3().fromBufferAttribute(positions, i), world: new Vector3().fromBufferAttribute(positions, i).applyMatrix4(child.matrixWorld) })
      }
    })
    gltf.scene.setJointValue(control.name, control.max !== 0 ? control.max * 0.6 : control.min * 0.6)
    gltf.scene.updateMatrixWorld(true)
    assert.ok(samples.some(s => s.local.clone().applyMatrix4(s.mesh.matrixWorld).distanceTo(s.world) > 1e-5), control.name)
    gltf.scene.setJointValue(control.name, 0)
    gltf.scene.updateMatrixWorld(true)
    assert.ok(samples.every(s => s.local.clone().applyMatrix4(s.mesh.matrixWorld).distanceTo(s.world) < 1e-8), `reset ${control.name}`)
  }
  gltf.scene.traverse(n => { n.geometry?.dispose(); if (n.material) for (const m of Array.isArray(n.material) ? n.material : [n.material]) m.dispose() })
})

// Solve against the real six-axis hierarchy, including a transformed model root.
test('Core tool dragging converges, respects preview guards, and resets', async () => {
  const { createCoreIK } = await import('../docs/.vitepress/theme/components/core-ik.mjs')
  const model = catalog.models.find(m => m.id === 'tech-core')
  const data = gunzipSync(fs.readFileSync(new URL(model.file, root)))
  const gltf = await new GLTFLoader().parseAsync(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength), '')
  const { controls, nodes } = bindCatalogJoints(gltf, model)
  gltf.scene.rotation.set(0.3, -0.2, 0.5)
  gltf.scene.position.set(1, 2, -0.4)
  const ik = createCoreIK(gltf.scene, model, controls, nodes)
  const rest = ik.position()
  for (const control of controls) {
    assert.equal(control.min, -1.2)
    assert.equal(control.max, 1.2)
    const node = nodes.get(control.name)
    assert.deepEqual(node.userData.rm.joint.preview_range, [-1.2, 1.2])
    assert.equal(node.userData.rm.joint.limits_status, 'unknown')
    for (const value of [-2, -1.2, 1.2, 2]) {
      gltf.scene.setJointValue(control.name, value)
      assert.ok(ik.position().toArray().every(Number.isFinite))
      assert.ok(Math.abs(node.quaternion.angleTo(node.quaternion.clone().setFromAxisAngle(new Vector3(...model.joints.find(j => j.id === control.name).axis), Math.max(-1.2, Math.min(1.2, value))))) < 1e-7)
    }
    gltf.scene.setJointValue(control.name, 0)
  }
  for (const sign of [1, -1]) {
    controls.forEach((c, i) => gltf.scene.setJointValue(c.name, sign * (i % 2 ? 0.30 : 0.40)))
    const target = ik.position()
    controls.forEach(c => { c.value = 0; gltf.scene.setJointValue(c.name, 0) })
    const initial = ik.position().distanceTo(target)
    const result = ik.solve(target)
    assert.ok(initial > 0.005)
    assert.ok(result.reached, `residual ${result.error}`)
    assert.ok(ik.position().distanceTo(target) <= 0.0005)
  }
  const far = rest.clone().add(new Vector3(10, 10, 10))
  const before = ik.position().distanceTo(far)
  const result = ik.solve(far)
  assert.equal(result.reached, false)
  assert.ok(result.error <= before)
  assert.ok(controls.every(c => Number.isFinite(c.value) && c.value >= c.min && c.value <= c.max))
  assert.throws(() => ik.solve(new Vector3(NaN, 0, 0)), /Invalid/)
  controls.forEach(c => { c.value = 0; gltf.scene.setJointValue(c.name, 0) })
  assert.ok(ik.position().distanceTo(rest) < 1e-9)
  assert.equal(createCoreIK(gltf.scene, { id: 'base' }, [], new Map()), null)
  gltf.scene.traverse(n => { n.geometry?.dispose(); if (n.material) for (const m of Array.isArray(n.material) ? n.material : [n.material]) m.dispose() })
})
