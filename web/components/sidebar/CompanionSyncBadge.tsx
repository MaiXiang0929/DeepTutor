"use client";

import { useEffect, useState } from "react";
import type { UserGameProfile } from "../../../packages/shared-protocol/src";
import { Bot, Zap } from "lucide-react";
import { loadGameProfile, PROFILE_CHANGED } from "@/shared/companion/rewards";

export function CompanionSyncBadge() {
  const [profile, setProfile] = useState<UserGameProfile | null>(null);
  useEffect(() => {
    let active: AbortController | undefined;
    function refresh() {
      active?.abort();
      const controller = new AbortController();
      active = controller;
      void loadGameProfile(controller.signal).then(profile => {
        if (!controller.signal.aborted) setProfile(profile);
      }).catch(() => {});
    }
    refresh();
    window.addEventListener(PROFILE_CHANGED, refresh);
    return () => {
      active?.abort();
      window.removeEventListener(PROFILE_CHANGED, refresh);
    };
  }, []);
  if (profile === null) return null;
  return (
    <span title="Companion energy" className="inline-flex shrink-0 items-center gap-1 rounded-full border border-[var(--border)] px-2 py-1 text-xs tabular-nums">
      {profile.companion
        ? <span aria-label={profile.companion.name}>{profile.companion.name.slice(0, 1)}</span>
        : <Bot aria-hidden size={15} />}
      <Zap aria-hidden size={13} />
      {profile.energy_points}
    </span>
  );
}
