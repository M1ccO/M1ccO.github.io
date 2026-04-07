export function createTransformDragState(object) {
  return {
    object,
    rawStartPosition: object.position.clone(),
    appliedStartPosition: object.position.clone(),
    lastRawPosition: object.position.clone(),
    appliedPosition: object.position.clone(),
    translationCarry: { x: 0, y: 0, z: 0 },
    fineTranslateActive: false,
    rawStartRotation: object.rotation.clone(),
    appliedStartRotation: object.rotation.clone(),
    lastRawRotation: object.rotation.clone(),
    appliedRotation: object.rotation.clone(),
    lastRawQuaternion: object.quaternion.clone(),
    appliedQuaternion: object.quaternion.clone(),
    rotationCarryDegrees: { x: 0, y: 0, z: 0 },
    fineRotateActive: false,
  };
}

export function createSelectionProxyDragState(selectionProxy) {
  return {
    position: selectionProxy.position.clone(),
    quaternion: selectionProxy.quaternion.clone(),
  };
}

export function resetFineTranslateAccumulator(state, object) {
  if (!state) {
    return;
  }
  state.rawStartPosition.copy(object.position);
  state.appliedStartPosition.copy(object.position);
  state.lastRawPosition.copy(object.position);
  state.appliedPosition.copy(object.position);
  state.translationCarry = { x: 0, y: 0, z: 0 };
  state.fineTranslateActive = false;
}

export function resetFineRotateAccumulator(state, object) {
  if (!state) {
    return;
  }
  state.rawStartRotation.copy(object.rotation);
  state.appliedStartRotation.copy(object.rotation);
  state.lastRawRotation.copy(object.rotation);
  state.appliedRotation.copy(object.rotation);
  state.lastRawQuaternion.copy(object.quaternion);
  state.appliedQuaternion.copy(object.quaternion);
  state.rotationCarryDegrees = { x: 0, y: 0, z: 0 };
  state.fineRotateActive = false;
}
