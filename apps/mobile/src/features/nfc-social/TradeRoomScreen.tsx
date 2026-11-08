import { useEffect, useRef, useState } from "react";
import { AppState, Button, ScrollView, Text, View } from "react-native";
import type { QuickEmoteId, TradeCommand, TradeSessionState, UserGameProfile } from "@deeptutor/shared-protocol";
import { post, type TutorClient } from "../../client";
import { GuardianControlScreen } from "../guardian/GuardianControlScreen";
import { ProximityHandshakeManager } from "./ProximityHandshakeManager";

const EMOTES: Record<QuickEmoteId, string> = {thumbs_up: "👍", please: "🙏", thank_you: "谢谢", wow: "哇"};
const TRADE = "/api/v1/trade";
const ink = {color: "#e0e7ff"};
type Question = {
  expires_at: number; answered: boolean; finished: boolean;
  question: {question: string; options: Record<string, string>};
  scores?: Partial<Record<"initiator" | "responder", number>>;
};

export function TradeRoomScreen({client}: {client: TutorClient}) {
  const manager = useRef<ProximityHandshakeManager | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const [phase, setPhase] = useState("准备近场交换");
  const [room, setRoom] = useState<TradeSessionState | null>(null);
  const [profile, setProfile] = useState<UserGameProfile | null>(null);
  const [offer, setOffer] = useState<Record<string, number>>({});
  const [guardian, setGuardian] = useState(false);
  const [connected, setConnected] = useState(false);
  const [question, setQuestion] = useState<Question | null>(null);
  const [quizRemaining, setQuizRemaining] = useState(0);
  const [answerPending, setAnswerPending] = useState(false);

  useEffect(() => {
    const lifecycle = AppState.addEventListener("change", state => {
      if (state !== "active") {
        void manager.current?.stop();
        socket.current?.close();
        manager.current = null;
      }
    });
    return () => {
      lifecycle.remove();
      void manager.current?.stop();
      socket.current?.close();
    };
  }, []);

  const roomId = room?.session_id;
  useEffect(() => {
    if (!roomId) return;
    const controller = new AbortController();
    void client.json<UserGameProfile>("/api/v1/gamification/profile", {signal: controller.signal})
      .then(next => { if (!controller.signal.aborted) setProfile(next); })
      .catch(e => { if (!controller.signal.aborted) setPhase(String(e)); });
    return () => controller.abort();
  }, [client, roomId]);

  useEffect(() => {
    if (!question || !roomId) return;
    const expiresAt = question.expires_at * 1000;
    function tick() { setQuizRemaining(Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000))); }
    tick();
    const timer = setInterval(tick, 250);
    if (question.finished) return () => clearInterval(timer);
    const controller = new AbortController();
    const poll = setInterval(() => {
      void client.json<Question>(`${TRADE}/${roomId}/partner-hangout`, {signal: controller.signal}).then(next => {
        if (!controller.signal.aborted && next.finished) setQuestion(next);
      }).catch(() => {});
    }, 1000);
    return () => { clearInterval(timer); clearInterval(poll); controller.abort(); };
  }, [client, question, roomId]);

  function connect(next: TradeSessionState) {
    setRoom(next);
    setOffer({});
    setQuestion(null);
    setAnswerPending(false);
    socket.current?.close();
    const ws = socket.current = client.socket(`/ws?trade_session_id=${encodeURIComponent(next.session_id)}`);
    ws.onopen = () => { if (socket.current === ws) setConnected(true); };
    ws.onclose = () => { if (socket.current === ws) setConnected(false); };
    ws.onmessage = event => {
      if (socket.current !== ws) return;
      try {
        const frame = JSON.parse(event.data);
        if (frame.type === "trade:state" || frame.type === "trade:completed") setRoom(frame.state);
        if (frame.type === "trade:error") setPhase(frame.message);
      } catch {
        setPhase("无法读取交易状态");
      }
    };
    ws.onerror = () => setPhase("交易房间连接中断");
  }

  async function start() {
    await manager.current?.stop();
    const next = new ProximityHandshakeManager(client, connect, setPhase);
    manager.current = next;
    try {
      await next.start();
    } catch (e) {
      setPhase(String(e));
    }
  }

  function send(value: TradeCommand) {
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(value));
    else setPhase("交易房间未连接");
  }

  async function hangout() {
    if (!roomId) return;
    try {
      setQuestion(await client.json<Question>(`${TRADE}/${roomId}/partner-hangout`, post({})));
    } catch (e) {
      setPhase(String(e));
    }
  }

  async function answerQuiz(option: string) {
    if (!roomId || answerPending) return;
    setAnswerPending(true);
    try {
      setQuestion(await client.json<Question>(`${TRADE}/${roomId}/partner-hangout/answer`, post({option})));
    } catch (e) {
      setPhase(String(e));
    } finally {
      setAnswerPending(false);
    }
  }

  if (guardian) return <View style={{flex: 1}}>
    <Button title="返回碰一碰" onPress={() => setGuardian(false)} />
    <GuardianControlScreen client={client} />
  </View>;

  const closed = room && ["cancelled", "expired", "completed"].includes(room.status);
  const theirs = room?.side === "initiator" ? room?.responder_items_json : room?.initiator_items_json;
  const mine = room?.side === "initiator" ? room?.initiator_items_json : room?.responder_items_json;
  const locked = room?.side === "initiator" ? room?.initiator_locked : room?.responder_locked;
  const confirmed = room?.side === "initiator" ? room?.initiator_confirmed : room?.responder_confirmed;
  const total = Object.values(offer).reduce((sum, quantity) => sum + quantity, 0);
  const items = profile?.inventory.reduce<Record<string, {name: string; quantity: number}>>((result, item) => {
    if (!item.is_equipped) {
      const entry = result[item.item_id] ?? {name: item.name, quantity: 0};
      result[item.item_id] = {...entry, quantity: entry.quantity + item.quantity};
    }
    return result;
  }, {}) ?? {};

  return <ScrollView contentContainerStyle={{padding: 18, gap: 12}}>
    <Text style={[ink, {fontSize: 26, fontWeight: "700"}]}>碰一碰社交</Text>
    <Button title="家长管控" onPress={() => {
      void manager.current?.stop();
      setGuardian(true);
    }} />
    <Text accessibilityRole="alert" style={ink}>{phase}</Text>
    {!room && <>
      <Button title="开始近场交换" onPress={() => void start()} />
      <Button title="读取 NFC 交换码" onPress={() => void manager.current?.readNfc().catch(e => setPhase(String(e)))} />
      <Button title="将临时交换码写入卡贴" onPress={() => void manager.current?.writeTag().catch(e => setPhase(String(e)))} />
    </>}
    {room && <>
      <Text style={ink}>交易状态 · {room.status}</Text>
      <Text style={ink}>同学 · {room.session_id.slice(-4).toUpperCase()}</Text>
      <Text style={ink}>对方学伴 · {room.peer_companion?.name ?? "访客"}</Text>
      <Text style={ink}>对方报价</Text>
      {Object.entries(theirs ?? {}).map(([id, quantity]) => <Text key={id} style={ink}>{id} ×{quantity}</Text>)}
      <Text style={ink}>己方已提交报价</Text>
      {Object.entries(mine ?? {}).map(([id, quantity]) => <Text key={id} style={ink}>{items[id]?.name ?? id} ×{quantity}</Text>)}
      {!closed && <>
        {!connected && <Button title="重新连接交易房间" onPress={() => connect(room)} />}
        <Text style={ink}>选择 1–3 件道具 · 已选 {total}</Text>
        {Object.entries(items).map(([id, item]) => <View key={id} style={{flexDirection: "row", gap: 7, alignItems: "center"}}>
          <Text style={ink}>{item.name} ×{item.quantity}</Text>
          <Button title="−" disabled={!offer[id]} onPress={() => setOffer(value => {
            const next = {...value};
            if (next[id] > 1) next[id] -= 1; else delete next[id];
            return next;
          })} />
          <Text style={ink}>{offer[id] ?? 0}</Text>
          <Button title="+" disabled={total >= 3 || (offer[id] ?? 0) >= item.quantity}
            onPress={() => setOffer(value => ({...value, [id]: (value[id] ?? 0) + 1}))} />
        </View>)}
        <Button title="提交报价" disabled={!total} onPress={() => send({type: "trade:update_offer", items: offer})} />
        <Button title={locked ? "已锁定" : "锁定"} disabled={locked || !Object.keys(mine ?? {}).length || !Object.keys(theirs ?? {}).length}
          onPress={() => send({type: "trade:lock", revision: room.revision})} />
        <Button title={confirmed ? "等待对方确认" : "确认交换"} disabled={confirmed || room.status !== "locked"}
          onPress={() => send({type: "trade:confirm", revision: room.revision})} />
        <View style={{flexDirection: "row", gap: 7}}>
          {(Object.keys(EMOTES) as QuickEmoteId[]).map(id => <Button key={id} title={EMOTES[id]}
            onPress={() => send({type: "trade:quick_emote", emote_id: id})} />)}
        </View>
        {room.quick_emote && <Text style={ink}>{EMOTES[room.quick_emote.emote_id]}</Text>}
        <Button title="取消交换" onPress={() => send({type: "trade:cancel"})} />
      </>}
      {room.status === "completed" && <>
        {room.synthesis_unlocks.length > 0 && <Text style={ink}>可合成 {room.synthesis_unlocks.join("、")}</Text>}
        <Button title="伙伴合体串门" onPress={() => void hangout()} />
      </>}
      {closed && <Button title="返回近场交换" onPress={() => {setRoom(null); setQuestion(null);}} />}
    </>}
    {question && <>
      <View style={{flexDirection: "row", gap: 18}}>
        <Text style={ink}>✦ {profile?.companion?.name ?? "我的学伴"}</Text>
        <Text style={ink}>✧ {room?.peer_companion?.name ?? "对方学伴"}</Text>
      </View>
      <Text style={ink}>双人抢答 · {quizRemaining} 秒</Text>
      <Text style={ink}>{question.question.question}</Text>
      {Object.entries(question.question.options ?? {}).map(([key, value]) => (
        <Button key={key} title={value} disabled={answerPending || question.answered || question.finished || !quizRemaining}
          onPress={() => void answerQuiz(key)} />
      ))}
      {question.finished && room && <Text style={ink}>我的得分 {question.scores?.[room.side] ?? 0} · 对方得分 {question.scores?.[room.side === "initiator" ? "responder" : "initiator"] ?? 0}</Text>}
      {question.answered && !question.finished && <Text style={ink}>已提交，等待对方作答</Text>}
    </>}
  </ScrollView>;
}
