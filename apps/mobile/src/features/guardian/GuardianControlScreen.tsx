import { useEffect, useState } from "react";
import { Button, ScrollView, Text, TextInput, View } from "react-native";
import type { TutorClient } from "../../client";

type Learner = {learner_user_id: string; learner_username: string; permissions: string[]};
type Day = {date: string; study_seconds: number; reward_count: number};
type Limits = {game_minutes: number; trades: number; pin_set: boolean};
const ROOT = "/api/v1/game-guardian";
const label = {color: "#e0e7ff"};
const field = {...label, borderColor: "#615c8e", borderWidth: 1, padding: 10, borderRadius: 8};

export function GuardianControlScreen({client}: {client: TutorClient}) {
  const [learners, setLearners] = useState<Learner[]>([]);
  const [selected, setSelected] = useState<Learner | null>(null);
  const [minutes, setMinutes] = useState("60");
  const [trades, setTrades] = useState("10");
  const [pin, setPin] = useState("");
  const [pinSet, setPinSet] = useState(false);
  const [days, setDays] = useState<Day[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void client.json<{relationships: Learner[]}>("/api/multi-user/me/guardianships", {signal: controller.signal})
      .then(result => { if (!controller.signal.aborted) setLearners(result.relationships); })
      .catch(() => { if (!controller.signal.aborted) setError("请使用有监护权限的账号登录。"); });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    const url = `${ROOT}/${encodeURIComponent(selected.learner_user_id)}`;
    const signal = controller.signal;
    if (selected.permissions.includes("manage_restrictions")) {
      void client.json<Limits>(url + "/limits", {signal}).then(limits => {
        if (signal.aborted) return;
        setMinutes(String(limits.game_minutes));
        setTrades(String(limits.trades));
        setPinSet(limits.pin_set);
      }).catch(e => { if (!signal.aborted) setError(String(e)); });
    }
    if (selected.permissions.includes("view_reports")) {
      void client.json<{days: Day[]}>(url + "/weekly-report", {signal})
        .then(report => { if (!signal.aborted) setDays(report.days); })
        .catch(e => { if (!signal.aborted) setError(String(e)); });
    }
    return () => controller.abort();
  }, [selected, client]);

  async function save() {
    if (!selected || busy) return;
    setBusy(true);
    try {
      const result = await client.json<Limits>(`${ROOT}/${encodeURIComponent(selected.learner_user_id)}/limits`, {
        method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({pin, game_minutes: Number(minutes), trades: Number(trades)}),
      });
      setPinSet(result.pin_set);
      setError("已保存每日额度");
    } catch (e) {
      setError(String(e));
    } finally {
      setPin("");
      setBusy(false);
    }
  }

  const maximumStudy = Math.max(1, ...days.map(day => day.study_seconds));
  const maximumRewards = Math.max(1, ...days.map(day => day.reward_count));
  return <ScrollView contentContainerStyle={{padding: 18, gap: 12}} keyboardShouldPersistTaps="handled">
    <Text style={[label, {fontSize: 24, fontWeight: "700"}]}>家长管控</Text>
    {learners.map(learner => <Button key={learner.learner_user_id}
      title={learner.learner_username}
      onPress={() => {
        setError(""); setDays([]); setPin(""); setSelected(learner);
      }} />)}
    {selected?.permissions.includes("manage_restrictions") && <>
      <Text style={label}>每日小游戏时长（0–60 分钟）</Text>
      <TextInput accessibilityLabel="每日小游戏时长" style={field} keyboardType="number-pad" value={minutes} onChangeText={setMinutes} />
      <Text style={label}>每日线下交换次数（0–10）</Text>
      <TextInput accessibilityLabel="每日交换次数" style={field} keyboardType="number-pad" value={trades} onChangeText={setTrades} />
      <Text style={label}>{pinSet ? "输入家长 PIN" : "设置六位家长 PIN"}</Text>
      <TextInput accessibilityLabel="家长 PIN" style={field} secureTextEntry keyboardType="number-pad" maxLength={6} value={pin} onChangeText={setPin} />
      <Button title="保存" disabled={busy || !/^\d{6}$/.test(pin) || !/^\d+$/.test(minutes) || Number(minutes) > 60 || !/^\d+$/.test(trades) || Number(trades) > 10} onPress={() => void save()} />
    </>}
    {days.length > 0 && <Text style={label}>过去七天 · 学习时长与陪伴奖励</Text>}
    {days.map(day => <View key={day.date} style={{gap: 3}}>
      <Text style={label}>{day.date} · 学习 {Math.round(day.study_seconds / 60)} 分钟 · {day.reward_count} 次奖励</Text>
      <View style={{height: 6, width: `${day.study_seconds / maximumStudy * 100}%`, backgroundColor: "#818cf8", borderRadius: 3}} />
      <View style={{height: 6, width: `${day.reward_count / maximumRewards * 100}%`, backgroundColor: "#34d399", borderRadius: 3}} />
    </View>)}
    {error && <Text accessibilityRole="alert" style={label}>{error}</Text>}
  </ScrollView>;
}
