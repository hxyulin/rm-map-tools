import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { createHash } from 'node:crypto'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { Vector3 } from 'three'
import { bindCatalogJoints } from '../docs/.vitepress/theme/components/model-utils.mjs'

const root = new URL('../docs/public/models/', import.meta.url)
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
