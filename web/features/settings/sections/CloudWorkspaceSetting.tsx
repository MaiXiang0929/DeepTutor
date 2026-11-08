"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingRow, SettingSection, inputClass } from "@/components/settings/shared";

const STORAGE_KEY = "deeptutor:cloud-workspace-url";

function validatedWorkspace(raw: string): string | null {
  try {
    const url = new URL(raw.trim());
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
    return url.toString();
  } catch {
    return null;
  }
}

export function CloudWorkspaceSetting() {
  const { t } = useTranslation();
  const [saved, setSaved] = useState("");
  const [draft, setDraft] = useState("");
  useEffect(() => {
    const value = window.localStorage.getItem(STORAGE_KEY) ?? "";
    setSaved(value);
    setDraft(value);
  }, []);
  const valid = validatedWorkspace(draft);
  const link = validatedWorkspace(saved);

  return (
    <SettingSection
      title={t("Cloud workspace")}
      description={t("Use the same hosted DeepTutor workspace on your computer and phone to share learning progress and rewards.")}
    >
      <SettingRow
        title={t("Cloud Sync Server URL")}
        control={
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="url"
              aria-label={t("Cloud Sync Server URL")}
              className={inputClass}
              value={draft}
              placeholder="https://tutor.example.org"
              onChange={event => setDraft(event.target.value)}
            />
            <button
              type="button"
              disabled={draft !== "" && !valid}
              onClick={() => {
                const url = valid ?? "";
                window.localStorage.setItem(STORAGE_KEY, url);
                setSaved(url);
              }}
            >
              {t("Save")}
            </button>
            {link && <a href={link} target="_blank" rel="noopener noreferrer">{t("Open cloud workspace")}</a>}
          </div>
        }
      />
    </SettingSection>
  );
}
