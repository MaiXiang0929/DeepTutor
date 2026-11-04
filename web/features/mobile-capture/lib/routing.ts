export interface CaptureTarget {
  workspaceId: string;
  sessionId: string | null;
  sessionKey: string;
}

export function matchesTarget(capture: CaptureTarget, current: CaptureTarget): boolean {
  return capture.workspaceId === current.workspaceId && (
    capture.sessionId ? capture.sessionId === current.sessionId
      : !current.sessionId && capture.sessionKey === current.sessionKey
  );
}

/** Only clear the exact snapshot sent; arrivals during an async send are a new draft. */
export function remainingAfterSend<T extends { type: string }>(current: T[], sent: T[], keep: boolean): T[] {
  const snapshot = new Set(sent);
  return current.filter(item => !snapshot.has(item) || (keep && item.type !== "quote"));
}

export function captureTargetKey(target: CaptureTarget): string {
  return JSON.stringify([target.workspaceId, target.sessionId || target.sessionKey]);
}

export function recoverDraftTarget<T extends CaptureTarget & { pageInstance?: string; previousDraftKey?: string }>(
  capture: T, current: CaptureTarget, pageInstance: string, navigationType: string,
): T {
  if (capture.pageInstance !== pageInstance && ["reload", "back_forward"].includes(navigationType) &&
      !capture.sessionId && !current.sessionId && capture.workspaceId === current.workspaceId) {
    return { ...capture, previousDraftKey: capture.sessionKey, sessionKey: current.sessionKey, pageInstance };
  }
  return capture;
}

export function phoneAttachmentsForTarget<T extends { type: string; captureId?: string; captureTarget?: string }>(
  attachments: T[], target: string, promotedFrom?: string,
): T[] {
  return attachments.flatMap(item => {
    if (!item.captureId || item.captureTarget === target) return [item];
    if (promotedFrom && item.captureTarget === promotedFrom) return [{ ...item, captureTarget: target }];
    return [];
  });
}
