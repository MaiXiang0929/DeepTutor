import { useEffect, useState } from "react";
import { Button, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Canvas, Line, vec } from "@shopify/react-native-skia";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { usePushToTalk } from "../voice/usePushToTalk";
import { post, type TutorClient } from "../../client";

type Mode = "match" | "turtle";
type Tile = {id: string; label: string};
type Round = {
  id: string; mode: Mode; status: "active" | "completed" | "expired" | "lost";
  expires_at: number; version: number; score: number; coins: number; affinity: number;
  left?: Tile[]; right?: Tile[]; prompt?: string; explanation?: string; last_answer?: string;
};
const ROOT = "/api/v1/gamification/games";
const TILE_HEIGHT = 60;
const ink = {color: "#e0e7ff"};
const verdicts = {yes: "是", no: "否", unrelated: "无关"};

export function MiniGamesScreen({client}: {client: TutorClient}) {
  const [round, setRound] = useState<Round | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [line, setLine] = useState<{from: number; to: number} | null>(null);
  const [width, setWidth] = useState(0);
  const voice = usePushToTalk(client, setInput, setMessage);

  useEffect(() => {
    if (!round || round.status !== "active") return;
    const controller = new AbortController();
    let settling = false;
    function tick() {
      const left = Math.max(0, Math.ceil(round!.expires_at - Date.now() / 1000));
      setSeconds(left);
      if (!left && !settling) {
        settling = true;
        void client.json<Round>(`${ROOT}/${round!.id}`, {signal: controller.signal}).then(next => {
          if (!controller.signal.aborted) setRound(next);
        }).catch(() => { settling = false; });
      }
    }
    tick();
    const timer = setInterval(tick, 250);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [client, round]);

  async function command(path: string, body: unknown) {
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      setRound(await client.json<Round>(ROOT + path, post(body)));
      setInput("");
    } catch (error) {
      setMessage(path === "/start"
        ? "无法开局。每局需 15 点能量，并计入今日游戏时长。去电脑端完成一道学习练习可获得能量。"
        : String(error));
    } finally {
      setBusy(false);
    }
  }

  function begin(mode: Mode) {
    setLine(null);
    setSelected("");
    void command("/start", {mode, request_id: `${Date.now()}-${Math.random().toString(36).slice(2)}`});
  }

  function match(left: Tile, right: Tile, from: number, to: number) {
    if (!round || busy) return;
    setLine({from, to});
    setSelected("");
    void command(`/${round.id}/match`, {left: left.id, right: right.id, version: round.version});
  }

  function ask(guess: boolean) {
    if (!round || !input.trim()) return;
    void command(`/${round.id}/ask`, {question: input.trim(), guess, version: round.version});
  }

  return <ScrollView contentContainerStyle={{padding: 18, gap: 12}} keyboardShouldPersistTaps="handled">
    <Text style={[ink, {fontSize: 26, fontWeight: "700"}]}>脑力游乐场</Text>
    {round?.status !== "active" && <View style={{gap: 10}}>
      <Button title="科学海龟汤 · 15 能量" disabled={busy} onPress={() => begin("turtle")} />
      <Button title="学科闪电配对 · 15 能量" disabled={busy} onPress={() => begin("match")} />
    </View>}
    {round && <Text style={ink}>得分 {round.score} · 金币 {round.coins} · 亲密度 {round.affinity}</Text>}
    {round?.status === "active" && <Text style={ink}>剩余 {seconds} 秒</Text>}
    {round?.status === "active" && round.mode === "match" && (
      <View onLayout={event => setWidth(event.nativeEvent.layout.width)} style={{flexDirection: "row", gap: 14}}>
        {line && <Canvas pointerEvents="none" style={{position: "absolute", width, height: 6 * TILE_HEIGHT}}>
          <Line p1={vec(width / 2 - 18, line.from * TILE_HEIGHT + 25)}
            p2={vec(width / 2 + 18, line.to * TILE_HEIGHT + 25)} color="#a5b4fc" strokeWidth={3} />
        </Canvas>}
        <View style={{flex: 1}}>
          {round.left?.map((tile, index) => {
            const drag = Gesture.Pan().runOnJS(true).onEnd(event => {
              const to = Math.round(index + event.translationY / TILE_HEIGHT);
              const target = round.right?.[to];
              if (event.translationX > 40 && target) match(tile, target, index, to);
            });
            return <GestureDetector key={tile.id} gesture={drag}><Pressable onPress={() => setSelected(tile.id)}
              style={{height: TILE_HEIGHT, justifyContent: "center", opacity: selected === tile.id ? 0.6 : 1}}>
              <Text style={ink}>{tile.label}</Text>
            </Pressable></GestureDetector>;
          })}
        </View>
        <View style={{flex: 1}}>{round.right?.map((tile, index) => <Pressable
          key={tile.id} style={{height: TILE_HEIGHT, justifyContent: "center"}}
          onPress={() => {
            const from = round.left?.findIndex(item => item.id === selected) ?? -1;
            if (from >= 0 && round.left) match(round.left[from], tile, from, index);
          }}><Text style={ink}>{tile.label}</Text></Pressable>)}</View>
      </View>
    )}
    {round?.mode === "turtle" && <>
      <Text style={ink}>{round.prompt}</Text>
      {round.last_answer && <Text style={ink}>{verdicts[round.last_answer as keyof typeof verdicts]}</Text>}
      {round.status === "active" && <>
        <Text style={ink}>剩余 {10 - round.version} 次</Text>
        <TextInput style={{...ink, borderColor: "#615c8e", borderWidth: 1, padding: 10}}
          placeholder="向伙伴提问或提交你的推理" placeholderTextColor="#9ca3af"
          value={input} maxLength={300} onChangeText={setInput} />
        <View style={{flexDirection: "row", gap: 12, flexWrap: "wrap"}}>
          <Pressable accessibilityRole="button" disabled={busy} onPressIn={() => void voice.begin()} onPressOut={() => void voice.finish()}>
            <Text style={ink}>{voice.recording ? "松开转写" : "按住说话"}</Text>
          </Pressable>
          <Button title="和温度有关？" disabled={busy} onPress={() => setInput("这个现象和温度有关吗？")} />
          <Button title="和光有关？" disabled={busy} onPress={() => setInput("这个现象和光有关吗？")} />
        </View>
        <Button title="提问" disabled={busy || !input.trim()} onPress={() => ask(false)} />
        <Button title="猜谜底" disabled={busy || !input.trim()} onPress={() => ask(true)} />
      </>}
      {round.explanation && <Text style={ink}>{round.explanation}</Text>}
    </>}
    {message ? <Text accessibilityRole="alert" style={ink}>{message}</Text> : null}
  </ScrollView>;
}
