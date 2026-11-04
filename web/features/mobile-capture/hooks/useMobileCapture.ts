"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { apiFetch, apiUrl, requestJson } from "@/shared/api/client";
import { browserStorage } from "@/shared/storage";
import { fileToPendingAttachment, type PendingAttachment } from "@/features/chat/controllers/pending-attachments";
import { captureTargetKey, matchesTarget, recoverDraftTarget, type CaptureTarget } from "../lib/routing";

const STORAGE = "dt-mobile-capture-v1";
const CLIENT = "dt-mobile-capture-client-v1";
const imported = new Set<string>();
const PAGE_INSTANCE = typeof window === "undefined" ? "server" :
  Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");

export interface CaptureSession extends CaptureTarget {
  pageInstance: string;
  previousDraftKey?: string;
  id: string;
  title: string;
  expires_at: number;
  local: boolean;
  links: { url: string; qr: string }[];
}

interface Receipt {
  id: string;
  filename: string;
  size: number;
  state: "received" | "attached" | "consumed";
}

interface CaptureStatus {
  active: boolean;
  paused: boolean;
  expires_at: number;
  files: Receipt[];
}

interface Options extends CaptureTarget {
  ready: boolean;
  boundFromKey: string | null;
  title: string;
  onReceive: (photo: PendingAttachment, target: CaptureTarget) => boolean;
}

function clientKey(): string {
  let key = browserStorage.readRaw("session", CLIENT);
  if (!key) {
    key = Array.from(crypto.getRandomValues(new Uint8Array(32)), byte => byte.toString(16).padStart(2, "0")).join("");
    if (!browserStorage.writeRaw("session", CLIENT, key)) throw new Error("Browser storage is unavailable.");
  }
  return key;
}

function headers(json = false): Record<string, string> {
  return { "X-Capture-Client": clientKey(), ...(json ? { "Content-Type": "application/json" } : {}) };
}

function persist(session: CaptureSession | null) {
  if (session) browserStorage.writeRaw("session", STORAGE, JSON.stringify(session));
  else browserStorage.removeRaw("session", STORAGE);
}

function consumedPhotos(id: string): Set<string> {
  try {
    const value: unknown = JSON.parse(browserStorage.readRaw("session", `${STORAGE}:consumed:${id}`) || "[]");
    return new Set(Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []);
  } catch { return new Set(); }
}

export function useMobileCapture(options: Options) {
  const [session, setSession] = useState<CaptureSession | null>(null);
  const [status, setStatus] = useState<CaptureStatus | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const live = useRef(options);
  const sessionRef = useRef(session);
  const initialRecovery = useRef<CaptureSession | null>(null);

  useEffect(() => {
    try {
      const raw = browserStorage.readRaw("session", STORAGE);
      if (raw) {
        setSession(JSON.parse(raw));
      }
    } catch { browserStorage.removeRaw("session", STORAGE); }
  }, []);

  const recoverInitialDraft = useCallback((sessionKey: string, workspaceId: string) => {
    const raw = browserStorage.readRaw("session", STORAGE);
    if (!raw) return;
    try {
      const previous: CaptureSession = initialRecovery.current || JSON.parse(raw);
      const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
      const recovered = recoverDraftTarget(previous, { workspaceId, sessionId: null, sessionKey },
        PAGE_INSTANCE, navigation?.type || "navigate");
      if (recovered !== previous) {
        initialRecovery.current = previous;
        persist(recovered);
        sessionRef.current = recovered;
        setSession(recovered);
      }
    } catch { /* Invalid storage is discarded by the initial restore. */ }
  }, []);

  useLayoutEffect(() => {
    if (captureTargetKey(live.current) !== captureTargetKey(options)) imported.clear();
    live.current = options;
    sessionRef.current = session;
    // The chat adapter records the draft key that became this server session.
    // Never infer this migration merely from whichever conversation is visible.
    if (session && !session.sessionId && options.sessionId &&
        options.workspaceId === session.workspaceId && options.boundFromKey === session.sessionKey) {
      const next = { ...session, sessionId: options.sessionId, sessionKey: options.sessionKey };
      persist(next);
      sessionRef.current = next;
      setSession(next);
    }
  }, [options, session]);

  const end = useCallback(async () => {
    const current = sessionRef.current;
    if (!current) return;
    try {
      await requestJson(apiUrl(`/api/mobile-capture/sessions/${current.id}`), { method: "DELETE", headers: headers() });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      throw cause;
    }
    persist(null);
    sessionRef.current = null;
    setSession(null);
    setStatus(null);
    setError("");
  }, []);

  const consume = useCallback((photos: PendingAttachment[]) => {
    const current = sessionRef.current;
    if (!current) return;
    const ids = consumedPhotos(current.id);
    for (const photo of photos) if (photo.captureId) ids.add(photo.captureId);
    browserStorage.writeRaw("session", `${STORAGE}:consumed:${current.id}`, JSON.stringify([...ids]));
    // Release requests are retried by the receipt poll if the connection fails.
    for (const photo of photos) if (photo.captureId) {
      void requestJson(apiUrl(`/api/mobile-capture/sessions/${current.id}/files/${photo.captureId}/consume`),
        { method: "POST", headers: headers() }).catch(() => {});
    }
  }, []);

  const restorePhoto = useCallback((photo: PendingAttachment): PendingAttachment | null => {
    if (!photo.captureId) return photo;
    const target = captureTargetKey(live.current);
    if (photo.captureTarget === target) return photo;
    const current = sessionRef.current;
    if (current?.previousDraftKey && matchesTarget(current, live.current) &&
        photo.captureTarget === captureTargetKey({ ...current, sessionId: null, sessionKey: current.previousDraftKey })) {
      return { ...photo, captureTarget: target };
    }
    return null;
  }, []);

  const start = useCallback(async () => {
    if (starting) return;
    setStarting(true);
    setError("");
    try {
      if (sessionRef.current) await end();
      const target = live.current;
      const data = await requestJson<Omit<CaptureSession, keyof CaptureTarget>>(apiUrl("/api/mobile-capture/sessions"), {
        method: "POST", headers: headers(true), body: JSON.stringify({
          target: `${target.workspaceId}:${target.sessionId || target.sessionKey}`,
          title: target.title, origin: window.location.origin,
        }),
      });
      const next: CaptureSession = { ...data, pageInstance: PAGE_INSTANCE, workspaceId: target.workspaceId,
        sessionId: target.sessionId, sessionKey: target.sessionKey };
      persist(next);
      sessionRef.current = next;
      setSession(next);
      setStatus(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setStarting(false); }
  }, [end, starting]);

  useEffect(() => {
    if (!session) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let paused: boolean | undefined;
    const path = `/api/mobile-capture/sessions/${session.id}`;
    const poll = async () => {
      try {
        const current = sessionRef.current;
        if (!current || current.id !== session.id) return;
        const shouldPause = !live.current.ready || !matchesTarget(current, live.current);
        if (paused !== shouldPause) {
          await requestJson(apiUrl(path), { method: "PATCH", headers: headers(true),
            body: JSON.stringify({ paused: shouldPause }), signal: abort.signal });
          paused = shouldPause;
        }
        const value = await requestJson<CaptureStatus>(apiUrl(path), { headers: headers(), cache: "no-store", signal: abort.signal });
        if (abort.signal.aborted) return;
        setStatus(value);
        setError("");
        const consumed = consumedPhotos(session.id);
        for (const photo of value.files.filter(file => file.state !== "consumed" && consumed.has(file.id))) {
          await requestJson(apiUrl(`${path}/files/${photo.id}/consume`), { method: "POST", headers: headers(), signal: abort.signal });
        }
        if (shouldPause) { imported.clear(); return; }
        for (const photo of value.files.filter(file => file.state !== "consumed" && !consumed.has(file.id))) {
          if (abort.signal.aborted || !sessionRef.current || !matchesTarget(sessionRef.current, live.current)) break;
          if (!imported.has(photo.id)) {
            const response = await apiFetch(apiUrl(`${path}/files/${photo.id}`), { headers: headers(), signal: abort.signal });
            if (!response.ok) throw new Error("Could not receive phone photo.");
            const pending = await fileToPendingAttachment(new File([await response.blob()], photo.filename, { type: "image/jpeg" }));
            if (abort.signal.aborted || !sessionRef.current || !live.current.ready || !matchesTarget(sessionRef.current, live.current)) break;
            if (consumedPhotos(session.id).has(photo.id)) continue;
            if (!live.current.onReceive({ ...pending, captureId: photo.id,
              captureTarget: captureTargetKey(sessionRef.current) }, sessionRef.current)) {
              setError("Send or remove attachments on the computer to receive more photos.");
              break;
            }
            imported.add(photo.id);
          }
          await requestJson(apiUrl(`${path}/files/${photo.id}/ack`), { method: "POST", headers: headers(), signal: abort.signal });
        }
      } catch (cause) {
        if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        if (!abort.signal.aborted) timer = setTimeout(() => void poll(), 2000);
      }
    };
    void poll();
    return () => { abort.abort(); imported.clear(); if (timer) clearTimeout(timer); };
  }, [session]);

  return { session, status, error, starting, start, end, consume, restorePhoto, recoverInitialDraft,
    paused: session ? !matchesTarget(session, options) : false };
}
