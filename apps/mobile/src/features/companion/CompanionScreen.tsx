import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, Button, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { File, Paths } from "expo-file-system";
import type { CompanionGreeting, EmotionState, UserGameProfile } from "@deeptutor/shared-protocol";
import { post, type TutorClient } from "../../client";
import { CompanionAvatarCanvas } from "./CompanionAvatarCanvas";
import { usePushToTalk } from "../voice/usePushToTalk";
import { decodePartnerReply } from "./emotions";

type Persona = "cyber_navigator" | "pixel_alchemist" | "oriental_spirit";
type Message = { id: number; text: string; own: boolean };
const PERSONAS = [
  ["cyber_navigator", "星澈"], ["pixel_alchemist", "艾可"], ["oriental_spirit", "云螭"],
] as const;

export function CompanionScreen({ client }: { client: TutorClient }) {
  const [light, setLight] = useState(false);
  const themeText = light ? styles.lightText : null;
  const [persona, setPersona] = useState<Persona>("cyber_navigator");
  const [partnerId, setPartnerId] = useState("");
  const [greeting, setGreeting] = useState<CompanionGreeting | null>(null);
  const [emotion, setEmotion] = useState<EmotionState>("idle");
  const [draft, setDraft] = useState("");
  const [replyProgress, setReplyProgress] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [rewardOpened, setRewardOpened] = useState(false);
  const audioFile = useRef<File | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const sequence = useRef(0);
  const {recording, begin, finish} = usePushToTalk(client, setDraft, setError);
  const player = useAudioPlayer(null);
  const audioStatus = useAudioPlayerStatus(player);

  const refresh = useCallback(async (signal: AbortSignal) => {
    try {
      const next = await client.json<CompanionGreeting>(
        "/api/v1/companion/proactive-greeting", {...post({persona}), signal},
      );
      if (signal.aborted) return;
      setGreeting(next);
      setEmotion(next.emotion_state);
    } catch (e) {
      if (!signal.aborted) setError(String(e));
    }
  }, [client, persona]);

  useEffect(() => {
    let controller = new AbortController();
    void refresh(controller.signal);
    const subscription = AppState.addEventListener("change", state => {
      if (state !== "active") return;
      controller.abort();
      controller = new AbortController();
      void refresh(controller.signal);
    });
    return () => {
      controller.abort();
      subscription.remove();
    };
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    void client.json<UserGameProfile>("/api/v1/gamification/profile", {signal: controller.signal})
      .then(profile => {
        if (controller.signal.aborted || !profile.companion) return;
        setPartnerId(profile.companion.partner_id);
        setPersona(profile.companion.persona_id);
      }).catch(() => {});
    return () => controller.abort();
  }, [client]);

  useEffect(() => () => {
    socket.current?.close();
    if (audioFile.current?.exists) audioFile.current.delete();
  }, []);

  async function play(path: string, init?: RequestInit) {
    const response = await client.fetch(path, init);
    if (!response.ok) throw new Error("语音暂不可用");
    const mime = response.headers.get("content-type") ?? "";
    const extension = mime.includes("wav") ? "wav" : mime.includes("ogg") ? "ogg" : "mp3";
    const file = new File(Paths.cache, `companion-${Date.now()}.${extension}`);
    file.create();
    file.write(new Uint8Array(await response.arrayBuffer()));
    const previous = audioFile.current;
    audioFile.current = file;
    player.replace(file.uri);
    player.play();
    if (previous?.exists) previous.delete();
  }

  async function selectPersona(next: Persona) {
    setBusy(true);
    setError("");
    try {
      const partner = await client.json<{partner_id: string}>(`/api/v1/companion/presets/${next}`, post({}));
      setPersona(next);
      setPartnerId(partner.partner_id);
      setMessages([]);
      setRewardOpened(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function send(raw: string) {
    const content = raw.trim();
    if (!content || !partnerId || busy) return;
    setMessages(items => [...items, {id: ++sequence.current, text: content, own: true}]);
    setDraft("");
    setBusy(true);
    setError("");
    setEmotion("thinking");
    const session = socket.current = client.socket(`/ws/partners/${encodeURIComponent(partnerId)}`);
    const timeout = setTimeout(() => {
      setError("伙伴回复超时");
      session.close();
    }, 60_000);
    let final = "";
    session.onmessage = event => {
      if (typeof event.data !== "string") return;
      try {
        const frame = JSON.parse(event.data);
        if (frame.type === "ready") session.send(JSON.stringify({content, session_id: "mobile-treehole"}));
        if (frame.type === "stream_event" && frame.event?.type === "content") {
          setReplyProgress("伙伴正在回复…");
        }
        if (frame.type === "content" && typeof frame.content === "string") final += frame.content;
        if (frame.type === "error") setError("伙伴暂时无法回复");
        if (frame.type === "done") {
          const reply = decodePartnerReply(final);
          setEmotion(reply.emotion_state);
          if (reply.text) {
            setMessages(items => [...items, {id: ++sequence.current, text: reply.text, own: false}]);
            void play("/api/voice/tts", post({text: reply.text, format: "mp3"})).catch(e => setError(String(e)));
          }
          session.close();
        }
      } catch {
        setError("无法读取伙伴回复");
        session.close();
      }
    };
    session.onerror = () => setError("连接伙伴失败");
    session.onclose = () => {
      clearTimeout(timeout);
      setReplyProgress("");
      setBusy(false);
    };
  }

  async function rememberMessage() {
    const note = [...messages].reverse().find(message => message.own)?.text;
    if (!note || !partnerId) return;
    try {
      await client.json(`/api/v1/companion/${partnerId}/memory-note`, post({note: note.slice(0, 200)}));
      setError("已保存到伙伴记忆");
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <ScrollView style={light ? styles.lightPanel : undefined} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <Text style={[styles.title, themeText]}>伙伴基地</Text>
      <Button title={light ? "切换深色主题" : "切换清新主题"} onPress={() => setLight(value => !value)} />
      <View style={styles.personas}>
        {PERSONAS.map(([id, name]) => (
          <Button key={id} title={name} disabled={busy} onPress={() => void selectPersona(id)} />
        ))}
      </View>
      <CompanionAvatarCanvas emotion={emotion} speaking={audioStatus.playing} />
      <Text style={[styles.text, themeText]}>{greeting?.text}</Text>
      {greeting?.reward_bubble && (
        <Button
          title={rewardOpened ? "已查看学习奖励" : `查看 ${greeting.reward_bubble.item.name}`}
          onPress={() => {
            setRewardOpened(true);
            void play(greeting.audio_url).catch(e => setError(String(e)));
          }}
        />
      )}
      {!partnerId && <Text style={[styles.text, themeText]}>选择一位伙伴开始对话。</Text>}
      {messages.map(message => (
        <Text key={message.id} style={[styles.text, message.own && styles.own, light && styles.lightText, light && message.own && styles.lightOwn]}>{message.text}</Text>
      ))}
      <Text style={[styles.text, themeText]}>{replyProgress}</Text>
      <TextInput
        accessibilityLabel="树洞留言"
        placeholder="想和伙伴说什么？"
        placeholderTextColor="#9ca3af"
        value={draft}
        onChangeText={setDraft}
        maxLength={4000}
        style={[styles.input, themeText]}
      />
      <View style={styles.personas}>
        <Pressable disabled={busy} onPressIn={() => void begin()} onPressOut={() => void finish()}>
          <Text style={[styles.text, themeText]}>{recording ? "松开转写" : "按住说话"}</Text>
        </Pressable>
        <Button title="发送" disabled={!partnerId || busy || !draft.trim()} onPress={() => send(draft)} />
        <Button title="保存上一条到记忆" disabled={!messages.length || busy} onPress={() => void rememberMessage()} />
      </View>
      {error ? <Text accessibilityRole="alert" style={[styles.text, themeText]}>{error}</Text> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {padding: 18, gap: 12},
  title: {color: "#f3f4ff", fontSize: 28, fontWeight: "700"},
  text: {color: "#e0e7ff", fontSize: 16},
  own: {alignSelf: "flex-end", backgroundColor: "#343070", padding: 10, borderRadius: 10},
  input: {color: "#fff", borderColor: "#615c8e", borderWidth: 1, borderRadius: 12, padding: 12},
  lightPanel: {backgroundColor: "#f5efff"},
  lightText: {color: "#2e2353"},
  lightOwn: {backgroundColor: "#d7caff"},
  personas: {flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 12},
});
