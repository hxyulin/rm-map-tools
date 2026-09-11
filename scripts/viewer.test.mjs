import test from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'
import { Vector3 } from 'three'
import URDFLoader from 'urdf-loader'
import { demoUrdf, jointControls, resolveLocalFile, sdfToUrdf, readCatalogModel } from '../docs/.vitepress/theme/components/model-utils.mjs'

const { window } = new JSDOM()
Object.assign(globalThis, { DOMParser: window.DOMParser, Document: window.Document, Element: window.Element })

test('example rail and rotary sliders apply local transforms and enforce travel limits', () => {
  const robot = new URDFLoader().parse(demoUrdf)
  assert.deepEqual(jointControls(robot).map(j => [j.name, j.unit]), [['rail', 'm'], ['hinge', 'rad']])
  robot.setJointValue('rail', 0.28)
  robot.setJointValue('hinge', 0.7)
  robot.updateMatrixWorld(true)
  const position = robot.links.carriage.getWorldPosition(new Vector3())
  assert.ok(Math.abs(position.x - 0.28) < 1e-10)
  assert.ok(Math.abs(position.z - 0.14) < 1e-10)
  robot.setJointValue('rail', 10)
  assert.equal(robot.joints.rail.jointValue[0], 0.28)
  robot.setJointValue('rail', 0)
  assert.equal(robot.joints.rail.jointValue[0], 0)
})

const sdf = `<sdf version="1.11"><model name="equipment"><static>false</static>
<link name="base"><pose relative_to="__model__">1 2 3 0 0 1.5707963267948966</pose></link>
<link name="slide"><pose relative_to="__model__">1 3 3 0 0 1.5707963267948966</pose><visual name="v"><geometry><mesh><uri>meshes/slide.stl</uri></mesh></geometry><material><diffuse>1 0 0 1</diffuse></material></visual></link>
<joint name="rail" type="prismatic"><parent>base</parent><child>slide</child><pose relative_to="slide">0 0 0 0 0 0</pose><axis><xyz>1 0 0</xyz><limit><lower>-0.28</lower><upper>0.28</upper></limit></axis></joint>
</model></sdf>`

test('exported SDF model frames survive conversion at rest and nonzero joint coordinates', () => {
  const loader = new URDFLoader(); loader.loadMeshCb = () => {}
  const xml = sdfToUrdf(sdf)
  assert.match(xml, /filename="meshes\/slide.stl"/)
  const robot = loader.parse(xml)
  robot.updateMatrixWorld(true)
  assert.ok(robot.links.slide.getWorldPosition(new Vector3()).distanceTo(new Vector3(1, 3, 3)) < 1e-10)
  robot.setJointValue('rail', 0.2); robot.updateMatrixWorld(true)
  assert.ok(robot.links.slide.getWorldPosition(new Vector3()).distanceTo(new Vector3(1, 3.2, 3)) < 1e-10)
})

test('unsupported SDF frames and world inputs fail explicitly', () => {
  assert.throws(() => sdfToUrdf(sdf.replace('relative_to="__model__"', 'relative_to="other"')), /relative/)
  assert.throws(() => sdfToUrdf(sdf.replace('type="prismatic"', 'type="universal"')), /joint type/)
  assert.throws(() => sdfToUrdf('<sdf><world name="world"/></sdf>'), /Unsupported/)
  assert.throws(() => sdfToUrdf(sdf.replace('<xyz>', '<xyz expressed_in="__model__">')), /joint frame/)
  assert.throws(() => sdfToUrdf(sdf.replace('0 0 0 0 0 0</pose><axis>', '1 0 0 0 0 0</pose><axis>')), /coincide/)
})

test('local resource resolver handles relative paths, ROS prefixes, and ambiguous files', () => {
  const files = [
    { name: 'link.stl', webkitRelativePath: 'export/base/meshes/link.stl' },
    { name: 'link.stl', webkitRelativePath: 'export/rune/meshes/link.stl' }
  ]
  assert.equal(resolveLocalFile('meshes/link.stl', files, 'export/base/model.sdf'), files[0])
  assert.equal(resolveLocalFile('package://rm_map_equipment/rune/meshes/link.stl', files), files[1])
  assert.throws(() => resolveLocalFile('link.stl', files), /Ambiguous/)
  assert.throws(() => resolveLocalFile('missing.stl', files), /Missing/)
})

 test('catalog accepts gzip bytes and models already decompressed by the host', async () => {
  const { gzipSync } = await import('node:zlib')
  const bytes = Buffer.from('glTF model bytes')
  for (const body of [bytes, gzipSync(bytes)]) {
    const decoded = await readCatalogModel(new Response(body))
    assert.deepEqual(Buffer.from(decoded), bytes)
  }
})
