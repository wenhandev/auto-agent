export type ViewportPadding = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export const WORKFLOW_CANVAS_PADDING: ViewportPadding = {
  left: 200,
  right: 32,
  top: 32,
  bottom: 180,
};

const DEFAULT_NODE_WIDTH = 200;
/** Target node width as a fraction of usable canvas width at zoom 1. */
const NODE_WIDTH_RATIO = 0.5;
const MIN_ZOOM = 0.4;
const MAX_ZOOM = 1;
/** If full-height fit zoom falls below this fraction of comfortable zoom, top-align instead. */
const HEIGHT_FIT_TOLERANCE = 0.85;

export type LayoutBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export function computeWorkflowViewport(
  bounds: LayoutBounds,
  flowWidth: number,
  flowHeight: number,
  options?: {
    padding?: ViewportPadding;
    nodeWidth?: number;
  },
): { x: number; y: number; zoom: number } {
  const padding = options?.padding ?? WORKFLOW_CANVAS_PADDING;
  const nodeWidth = options?.nodeWidth ?? DEFAULT_NODE_WIDTH;
  const availW = flowWidth - padding.left - padding.right;
  const availH = flowHeight - padding.top - padding.bottom;

  if (availW <= 0 || availH <= 0 || bounds.width <= 0 || bounds.height <= 0) {
    return { x: 0, y: 0, zoom: 1 };
  }

  const zoomToFitWidth = availW / bounds.width;
  const zoomToFitHeight = availH / bounds.height;
  const readableZoom = Math.min(
    MAX_ZOOM,
    (availW * NODE_WIDTH_RATIO) / nodeWidth,
  );
  const comfortableZoom = Math.min(zoomToFitWidth, readableZoom);
  const fullFitZoom = Math.min(zoomToFitWidth, zoomToFitHeight);

  let zoom: number;
  let topAlign: boolean;

  if (fullFitZoom >= comfortableZoom * HEIGHT_FIT_TOLERANCE) {
    zoom = Math.max(MIN_ZOOM, Math.min(fullFitZoom, MAX_ZOOM));
    topAlign = false;
  } else {
    zoom = Math.max(MIN_ZOOM, Math.min(comfortableZoom, MAX_ZOOM));
    topAlign = true;
  }

  const centerX = bounds.x + bounds.width / 2;
  const x = padding.left + availW / 2 - centerX * zoom;

  const y = topAlign
    ? padding.top - bounds.y * zoom
    : padding.top + availH / 2 - (bounds.y + bounds.height / 2) * zoom;

  return { x, y, zoom };
}
