export function createMeasurementDragController(deps) {
  let dragState = null;
  let dragJustEnded = false;

  const getDragObjects = () => {
    if (typeof deps.getMeasurementDragObjects === 'function') {
      return deps.getMeasurementDragObjects();
    }
    if (typeof deps.getDistanceDragObjects === 'function') {
      return deps.getDistanceDragObjects();
    }
    return [];
  };

  const updatePointerRay = (event) => {
    const rect = deps.canvas.getBoundingClientRect();
    deps.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    deps.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    deps.raycaster.setFromCamera(deps.pointer, deps.camera);
  };

  const setDragEnded = () => {
    dragJustEnded = true;
    setTimeout(() => {
      dragJustEnded = false;
    }, 120);
  };

  return {
    didJustEnd() {
      return dragJustEnded;
    },

    onMouseDown(event) {
      if (!deps.isMeasurementsVisible() || !deps.isMeasurementDragEnabled() || event.button !== 0) {
        return false;
      }

      updatePointerRay(event);
      const dragTargets = getDragObjects();
      if (dragTargets.length === 0) {
        return false;
      }

      const intersects = deps.raycaster.intersectObjects(dragTargets, false);
      if (intersects.length === 0) {
        return false;
      }

      const hit = intersects[0];
      const dragKind = String(hit.object?.userData?.dragKind || '');
      const measurementIndex = Number(hit.object?.userData?.measurementIndex);
      const overlays = deps.getMeasurementOverlays();

      if (!Number.isInteger(measurementIndex) || measurementIndex < 0 || measurementIndex >= overlays.length) {
        return false;
      }

      const overlay = overlays[measurementIndex];
      const overlayType = String(overlay?.type || '').toLowerCase();
      if (!overlay || (overlayType !== 'distance' && overlayType !== 'diameter_ring')) {
        return false;
      }

      let axisDir = null;
      let originalOffset = null;
      if (overlayType === 'distance') {
        axisDir = deps.distanceDirectionForOverlay(overlay);
        if (!axisDir) {
          return false;
        }
        originalOffset = deps.parseOverlayVector(overlay.offset_xyz) || deps.defaultDistanceOffsetForOverlay(overlay);
      } else if (overlayType === 'diameter_ring') {
        if (dragKind !== 'diameter-offset') {
          return false;
        }
        originalOffset = deps.parseOverlayVector(overlay.offset_xyz) || deps.defaultDiameterOffsetForOverlay(overlay);
      }

      if (!originalOffset) {
        return false;
      }

      const plane = new deps.THREE.Plane();
      const planeNormal = deps.camera.getWorldDirection(new deps.THREE.Vector3()).normalize();
      plane.setFromNormalAndCoplanarPoint(planeNormal, hit.point.clone());

      const planeStartPoint = new deps.THREE.Vector3();
      if (!deps.raycaster.ray.intersectPlane(plane, planeStartPoint)) {
        return false;
      }

      dragState = {
        dragKind,
        overlayType,
        measurementIndex,
        axisDir,
        plane,
        planeStartPoint,
        originalOffset,
        originalStartShift: Number(overlay.start_shift) || 0,
        originalEndShift: Number(overlay.end_shift) || 0,
      };

      deps.setControlsEnabled(false);
      event.preventDefault();
      return true;
    },

    onMouseMove(event) {
      updatePointerRay(event);

      if (!dragState) {
        if (!deps.isMeasurementsVisible() || !deps.isMeasurementDragEnabled()) {
          deps.setCanvasCursor('');
          return;
        }

        const hoverTargets = getDragObjects();
        if (hoverTargets.length === 0) {
          deps.setCanvasCursor('');
          return;
        }

        const hoverIntersects = deps.raycaster.intersectObjects(hoverTargets, false);
        deps.setCanvasCursor(hoverIntersects.length > 0 ? 'grab' : '');
        return;
      }

      deps.setCanvasCursor('grabbing');

      const currentPoint = new deps.THREE.Vector3();
      if (!deps.raycaster.ray.intersectPlane(dragState.plane, currentPoint)) {
        return;
      }

      const delta = currentPoint.clone().sub(dragState.planeStartPoint);
      const overlays = deps.getMeasurementOverlays();
      const overlay = overlays[dragState.measurementIndex];
      if (!overlay) {
        return;
      }

      const snap = event.ctrlKey
        ? (v) => Math.round(Number(v) * 10) / 10
        : deps.snapMm;
      const snapVec = event.ctrlKey
        ? (v) => new deps.THREE.Vector3(snap(v.x), snap(v.y), snap(v.z))
        : deps.snapVec3Mm;

      if (dragState.dragKind === 'distance-offset') {
        const alongAxis = dragState.axisDir.clone().multiplyScalar(delta.dot(dragState.axisDir));
        const sidewaysDelta = delta.clone().sub(alongAxis);
        const newOffset = snapVec(dragState.originalOffset.clone().add(sidewaysDelta));
        overlay.offset_xyz = deps.formatVec3(newOffset);
      } else if (dragState.dragKind === 'diameter-offset') {
        const newOffset = snapVec(dragState.originalOffset.clone().add(delta));
        overlay.offset_xyz = deps.formatVec3(newOffset);
      } else if (dragState.dragKind === 'distance-start') {
        const shift = delta.dot(dragState.axisDir);
        overlay.start_shift = String(snap(dragState.originalStartShift + shift));
      } else if (dragState.dragKind === 'distance-end') {
        const shift = delta.dot(dragState.axisDir);
        overlay.end_shift = String(snap(dragState.originalEndShift + shift));
      }

      deps.scheduleMeasurementsRender();
      event.preventDefault();
    },

    onMouseUp() {
      if (!dragState) {
        return;
      }

      const updatedIndex = dragState.measurementIndex;
      dragState = null;
      deps.setControlsEnabled(true);
      deps.emitMeasurementUpdated(updatedIndex);
      deps.setCanvasCursor('');
      setDragEnded();
    },
  };
}
