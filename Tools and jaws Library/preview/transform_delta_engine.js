export function applySelectionProxyTransformDelta({
  mode,
  selectionProxy,
  selectionProxyDragState,
  selectedMeshIndices,
  currentMeshes,
  scene,
  THREE,
}) {
  if (!selectionProxyDragState || !Array.isArray(selectedMeshIndices) || selectedMeshIndices.length <= 0) {
    return false;
  }

  const previousPosition = selectionProxyDragState.position.clone();
  const previousQuaternion = selectionProxyDragState.quaternion.clone();
  const deltaPosition = selectionProxy.position.clone().sub(previousPosition);
  const deltaQuaternion = selectionProxy.quaternion.clone().multiply(previousQuaternion.clone().invert());

  if (mode === 'translate') {
    const worldPos = new THREE.Vector3();
    const targetWorldPos = new THREE.Vector3();
    for (const idx of selectedMeshIndices) {
      const mesh = currentMeshes[idx];
      if (!mesh) continue;
      const parent = mesh.parent || scene;
      mesh.getWorldPosition(worldPos);
      targetWorldPos.copy(worldPos).add(deltaPosition);
      mesh.position.copy(parent.worldToLocal(targetWorldPos.clone()));
    }
  } else {
    const worldPos = new THREE.Vector3();
    const targetWorldPos = new THREE.Vector3();
    const worldQuat = new THREE.Quaternion();
    const targetWorldQuat = new THREE.Quaternion();
    const parentWorldQuat = new THREE.Quaternion();
    const parentWorldQuatInv = new THREE.Quaternion();

    for (const idx of selectedMeshIndices) {
      const mesh = currentMeshes[idx];
      if (!mesh) continue;
      const parent = mesh.parent || scene;

      mesh.getWorldPosition(worldPos);
      targetWorldPos.copy(worldPos).sub(previousPosition).applyQuaternion(deltaQuaternion).add(previousPosition);
      mesh.position.copy(parent.worldToLocal(targetWorldPos.clone()));

      mesh.getWorldQuaternion(worldQuat);
      targetWorldQuat.copy(deltaQuaternion).multiply(worldQuat);
      parent.getWorldQuaternion(parentWorldQuat);
      parentWorldQuatInv.copy(parentWorldQuat).invert();
      mesh.quaternion.copy(parentWorldQuatInv.multiply(targetWorldQuat));
    }
  }

  selectionProxyDragState.position.copy(selectionProxy.position);
  selectionProxyDragState.quaternion.copy(selectionProxy.quaternion);
  return true;
}
