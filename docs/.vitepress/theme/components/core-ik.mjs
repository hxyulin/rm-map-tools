import { Box3, Quaternion, Vector3 } from 'three'

// Position-only CCD on the existing display rig. Catalog ranges are preview guards.
export function createCoreIK(object, model, controls, nodes) {
  if (model.id !== 'tech-core' || controls.length !== 6) return null
  let tool
  object.traverse(node => { if (node.userData.rm?.id === 'tech-core.part.tool.assembly') tool = node })
  if (!tool) throw new Error('The Core display rig has no tool assembly.')
  object.updateMatrixWorld(true)
  const center = new Box3().setFromObject(tool).getCenter(new Vector3())
  const local = tool.worldToLocal(center.clone())
  const position = () => { object.updateMatrixWorld(true); return tool.localToWorld(local.clone()) }
  const chain = controls.map((control, i) => ({ control, node: nodes.get(control.name), axis: new Vector3(...model.joints[i].axis) }))
  function solve(target, iterations = 80) {
    if (![target.x, target.y, target.z].every(Number.isFinite)) throw new Error('Invalid tool target.')
    let error = position().distanceTo(target)
    for (let pass = 0; pass < iterations && error > 0.0005; pass++) {
      const before = error
      for (const { control, node, axis } of [...chain].reverse()) {
        const origin = node.getWorldPosition(new Vector3())
        const worldAxis = axis.clone().applyQuaternion(node.parent.getWorldQuaternion(new Quaternion())).normalize()
        const from = position().sub(origin).projectOnPlane(worldAxis)
        const to = target.clone().sub(origin).projectOnPlane(worldAxis)
        if (from.lengthSq() < 1e-14 || to.lengthSq() < 1e-14) continue
        from.normalize(); to.normalize()
        const angle = Math.atan2(worldAxis.dot(from.clone().cross(to)), from.dot(to))
        control.value = Math.max(control.min, Math.min(control.max, control.value + Math.max(-0.12, Math.min(0.12, angle))))
        object.setJointValue(control.name, control.value)
        object.updateMatrixWorld(true)
      }
      error = position().distanceTo(target)
      if (before - error < 1e-9) break
    }
    return { error, reached: error <= 0.0005 }
  }
  return { position, solve }
}
