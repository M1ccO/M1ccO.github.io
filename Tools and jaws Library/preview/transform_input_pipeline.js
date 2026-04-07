function snapToStep(value, step) {
  const numericValue = Number(value) || 0;
  const numericStep = Math.abs(Number(step) || 0);
  if (numericStep <= 0) {
    return numericValue;
  }

  const snapped = Math.round(numericValue / numericStep) * numericStep;
  return Math.abs(snapped) < 1e-9 ? 0 : snapped;
}

export function applyTransformDragDamping({
  object,
  state,
  mode,
  axis,
  fineEnabled,
  gains,
}) {
  if (!state || state.object !== object) {
    return;
  }
  if (mode !== 'translate') {
    return;
  }

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
}
