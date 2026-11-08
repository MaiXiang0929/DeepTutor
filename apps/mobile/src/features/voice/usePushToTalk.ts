import { useEffect, useRef, useState } from "react";
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder } from "expo-audio";
import { File } from "expo-file-system";
import type { TutorClient } from "../../client";

export function usePushToTalk(client: TutorClient, onText: (text: string) => void, onError: (error: string) => void) {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const pressed = useRef(false);
  const started = useRef(false);
  const [recording, setRecording] = useState(false);

  useEffect(() => () => {
    pressed.current = false;
    void setAudioModeAsync({allowsRecording: false}).catch(() => {});
  }, []);

  async function begin() {
    if (pressed.current || started.current) return;
    pressed.current = true;
    try {
      if (!(await AudioModule.requestRecordingPermissionsAsync()).granted) {
        throw new Error("需要麦克风权限");
      }
      if (!pressed.current) return;
      await setAudioModeAsync({allowsRecording: true, playsInSilentMode: true});
      await recorder.prepareToRecordAsync();
      if (!pressed.current) {
        await recorder.stop();
        await setAudioModeAsync({allowsRecording: false});
        return;
      }
      recorder.record({forDuration: 30});
      started.current = true;
      setRecording(true);
    } catch (error) {
      pressed.current = false;
      onError(String(error));
    }
  }

  async function finish() {
    pressed.current = false;
    if (!started.current) return;
    setRecording(false);
    try {
      if (recorder.isRecording) await recorder.stop();
      await setAudioModeAsync({allowsRecording: false, playsInSilentMode: true});
      if (!recorder.uri) return;
      const audio = new File(recorder.uri);
      const form = new FormData();
      form.append("file", audio);
      form.append("language", "zh");
      try {
        const result = await client.json<{text: string}>("/api/voice/stt", {method: "POST", body: form});
        onText(result.text);
      } finally {
        if (audio.exists) audio.delete();
      }
    } catch (error) {
      onError(String(error));
    } finally {
      started.current = false;
    }
  }

  return {recording, begin, finish};
}
