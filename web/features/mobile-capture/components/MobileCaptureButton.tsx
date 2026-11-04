"use client";

import { useEffect, useRef, useState } from "react";
import { Smartphone, X, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMobileCapture } from "../hooks/useMobileCapture";

export type MobileCaptureControl = ReturnType<typeof useMobileCapture>;

export default function MobileCaptureButton({ capture }: { capture: MobileCaptureControl }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [address, setAddress] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const active = capture.status?.active ?? Boolean(capture.session);
  const link = capture.session?.links[address] ?? capture.session?.links[0];
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);

  return <>
    <button type="button" onClick={() => setOpen(true)}
      className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
      aria-label={t("Phone photo upload")}>
      <Smartphone size={15} />{active ? t("Receiving photos") : t("Phone photos")}
    </button>
    <dialog ref={dialog} onCancel={() => setOpen(false)} onClose={() => setOpen(false)}
      aria-labelledby="phone-capture-title" className="m-auto w-[min(94vw,440px)] rounded-2xl border border-[var(--border)] bg-[var(--background)] p-6 text-[var(--foreground)] shadow-xl backdrop:bg-black/35">
      <div className="flex items-center justify-between gap-3">
        <h2 id="phone-capture-title" className="text-lg font-semibold">{t("Phone photo upload")}</h2>
        <button type="button" onClick={() => setOpen(false)} aria-label={t("Close")} className="rounded p-1"><X size={18} /></button>
      </div>
      <p className="mt-3 text-sm text-[var(--muted-foreground)]">{t("Scan once and upload more photo batches to this conversation.")}</p>
      {capture.session && link ? <>
        <p className="mt-3 truncate text-sm font-medium">{capture.session.title}</p>
        {/* The SVG is generated locally by the backend QR library. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={link.qr} alt={t("Scan to upload phone photos")} width={240} height={240} className="mx-auto my-4 rounded-xl bg-white" />
        {capture.session.links.length > 1 && <label className="block text-sm">{t("Network address")}
          <select value={address} onChange={event => setAddress(Number(event.target.value))} className="mt-1 w-full rounded border border-[var(--border)] bg-[var(--background)] p-2">
            {capture.session.links.map((item, index) => <option key={item.url} value={index}>{new URL(item.url).host}</option>)}
          </select>
        </label>}
        <input readOnly value={link.url} aria-label={t("Phone upload link")} onFocus={event => event.currentTarget.select()}
          className="mt-2 w-full rounded border border-[var(--border)] bg-[var(--muted)] p-2 text-xs" />
        <p className="mt-3 text-sm" role="status">{!active ? t("Upload link expired. Create a new QR code.") : capture.paused ? t("Return to the target conversation to receive photos.") : t("Receiving photos")}</p>
        <p className="mt-1 text-xs text-[var(--muted-foreground)]">{t("Photos added")}: {capture.status?.files.filter(file => file.state !== "received").length ?? 0}</p>
        <p className="mt-1 text-xs text-[var(--muted-foreground)]">{t("Expires at")}: {new Date((capture.status?.expires_at ?? capture.session.expires_at) * 1000).toLocaleTimeString()}</p>
        {capture.session.local && <p className="mt-3 text-xs text-[var(--muted-foreground)]">{t("Use the same trusted Wi-Fi or hotspot. If connection fails, check the network address and firewall.")}</p>}
      </> : null}
      {capture.error && <p role="alert" className="mt-3 text-sm text-red-600">{t(capture.error)}</p>}
      <div className="mt-5 flex gap-3">
        <button type="button" disabled={capture.starting} onClick={() => { setAddress(0); void capture.start(); }}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--primary)] px-3 py-2 text-sm text-[var(--primary-foreground)] disabled:opacity-50">
          {capture.starting && <Loader2 size={15} className="animate-spin" />}{capture.session ? t("Refresh QR code") : t("Create QR code")}
        </button>
        {capture.session && <button type="button" onClick={() => void capture.end().catch(() => {})} className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm">{t("End receiving")}</button>}
      </div>
      <p className="mt-3 text-xs text-[var(--muted-foreground)]">{t("Closing this window keeps receiving. Use End receiving to disconnect.")}</p>
    </dialog>
  </>;
}
