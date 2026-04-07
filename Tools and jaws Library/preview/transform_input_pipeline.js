import * as THREE from './three.module.js';
import { resetFineRotateAccumulator, resetFineTranslateAccumulator } from './transform_state.js';

function snapMm(value) {
  return Math.round(Number(value) || 0);
}

function snapDegrees(value) {
  return Math.round(Number(value) || 0);
}

function snapToStep(value, step) {
  const numericValue = Number(value) || 0;
  const numericStep = Math.abs(Number(step) || 0);
  if (numericStep <= 0) {
    return numericValue;
  }

  const snapped = Math.round(numericValue / numericStep) * numericStep;
  return Math.abs(snapped) < 1e-9 ? 0 : snapped;
}

function extractSnappedDelta(carry, step) {
  const numericCarry = Number(carry) || 0;
  const numericStep = Math.abs(Number(step) || 0);
  if (numericStep <= 0) {
    return { snapped: 0, remainder: numericCarry };
  }

  const stepCount = numericCarry >= 0
    ? Math.floor(numericCarry / numericStep)
    : Math.ceil(numericCarry / numericStep);

  const snapped = stepCount * numericStep;
  let remainder = numericCarry - snapped;
  if (Math.abs(remainder) < 1e-9) {
    remainder = 0;
  }
  return { snapped, remainder };
}

function wrapSignedRadians(value) {
  return Math.atan2(Math.sin(value), Math.cos(value));
}

function axisVectorForName(axisName, THREE) {
  if (axisName === 'X') {
    return new THREE.Vector3(1, 0, 0);
  }
  if (axisName === 'Y') {
    return new THREE.Vector3(0, 1, 0);
  }
  return new THREE.Vector3(0, 0, 1);
}

function signedAngleAroundAxis(deltaQuaternion, axis) {
  const normalizedAxis = axis.clone().normalize();
  const projected = normalizedAxis.multiplyScalar(
    deltaQuaternion.x * normalizedAxis.x
    + deltaQuaternion.y * normalizedAxis.y
    + deltaQuaternion.z * normalizedAxis.z
  );
  const twist = new THREE.Quaternion(projected.x, projected.y, projected.z, deltaQuaternion.w).normalize();
  const twistVector = new THREE.Vector3(twist.x, twist.y, twist.z);
  return wrapSignedRadians(2 * Math.atan2(twistVector.dot(normalizedAxis), twist.w));
}

export function applyTransformDragDamping({
  object,
  state,
  mode,
  axis,
  space,
  fineEnabled,
  gains,
}) {
  if (!state || state.object !== object) {
    return;
  }
  if (mode !== 'translate' && mode !== 'rotate') {
    return;
  }

  if (mode === 'translate') {
    const rawPosition = object.position.clone();
    const gain = fineEnabled ? (Number(gains?.fineTranslate) || 0) : (Number(gains?.regularTranslate) || 0);
    const translationStep = fineEnabled ? 0.1 : 1;

    if (state.fineTranslateActive !== fineEnabled) {
      state.rawStartPosition.copy(rawPosition);
      state.appliedStartPosition.copy(state.appliedPosition);
      state.lastRawPosition.copy(rawPosition);
      object.position.copy(state.appliedStartPosition);
      state.fineTranslateActive = fineEnabled;
    }

    const currentAxis = String(axis || '').toUpperCase();
    const nextPosition = state.appliedStartPosition.clone();

    const isAxisActive = (axisKey) => {
      if (!currentAxis || currentAxis === 'XYZ' || currentAxis === 'E') {
        return true;
      }
      return currentAxis.includes(axisKey.toUpperCase());
    };

    const applyAxis = (axisKey) => {
      if (!isAxisActive(axisKey)) {
        state.translationCarry[axisKey] = 0;
        return;
      }

      const rawOffset = (rawPosition[axisKey] || 0) - (state.rawStartPosition[axisKey] || 0);
      const snappedOffset = snapToStep(rawOffset * gain, translationStep);
      nextPosition[axisKey] = (state.appliedStartPosition[axisKey] || 0) + snappedOffset;
    };

    applyAxis('x');
    applyAxis('y');
    applyAxis('z');

    state.lastRawPosition.copy(rawPosition);
    state.appliedPosition.copy(nextPosition);
    object.position.copy(nextPosition);
    return;
  }

  const currentAxis = String(axis || '').toUpperCase();
  const gain = fineEnabled ? (Number(gains?.fineRotate) || 0) : (Number(gains?.regularRotate) || 0);
  const rotationStep = fineEnabled ? 0.1 : 1;
  if (!fineEnabled && state.fineRotateActive) {
    resetFineRotateAccumulator(state, object);
  }
  if (fineEnabled && !state.fineRotateActive) {
    resetFineRotateAccumulator(state, object);
    state.fineRotateActive = true;
  } else if (!fineEnabled) {
    state.fineRotateActive = false;
  }
  const rawQuaternion = object.quaternion.clone();
  const deltaQuaternion = rawQuaternion.clone().multiply(state.lastRawQuaternion.clone().invert()).normalize();
  const nextQuaternion = state.appliedQuaternion.clone();
  const rotationDelta = new THREE.Quaternion();
  const currentSpace = String(space || '').toLowerCase() === 'world' ? 'world' : 'local';

  const applyAxisRotation = (axisName) => {
    const axisKey = axisName.toLowerCase();
    const localAxis = axisVectorForName(axisName, THREE);
    const worldAxis = currentSpace === 'local'
      ? localAxis.clone().applyQuaternion(state.lastRawQuaternion).normalize()
      : localAxis;
    const deltaDegrees = THREE.MathUtils.radToDeg(signedAngleAroundAxis(deltaQuaternion, worldAxis));
    const gainedDegrees = deltaDegrees * gain;
    const carryDegrees = (state.rotationCarryDegrees[axisKey] || 0) + gainedDegrees;
    const { snapped: snappedDegrees, remainder } = extractSnappedDelta(carryDegrees, rotationStep);
    state.rotationCarryDegrees[axisKey] = remainder;
    if (Math.abs(snappedDegrees) < 1e-9) {
      return;
    }
    rotationDelta.setFromAxisAngle(localAxis, THREE.MathUtils.degToRad(snappedDegrees));
    nextQuaternion.multiply(rotationDelta);
  };

  if (currentAxis === 'X' || currentAxis === 'Y' || currentAxis === 'Z') {
    applyAxisRotation(currentAxis);
  } else {
    applyAxisRotation('X');
    applyAxisRotation('Y');
    applyAxisRotation('Z');
  }

  state.lastRawQuaternion.copy(rawQuaternion);
  state.lastRawRotation.copy(object.rotation);
  state.appliedQuaternion.copy(nextQuaternion);
  object.quaternion.copy(nextQuaternion);
  state.appliedRotation.copy(object.rotation);
}
