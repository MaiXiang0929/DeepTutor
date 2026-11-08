import { GestureHandlerRootView } from "react-native-gesture-handler";
import { useState } from "react";
import { Button, Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from "react-native";
import { post, serverOrigin, TutorClient } from "./src/client";
import { TradeRoomScreen } from "./src/features/nfc-social/TradeRoomScreen";
import { InventoryScreen } from "./src/features/inventory/InventoryScreen";
import { MiniGamesScreen } from "./src/features/minigames/MiniGamesScreen";
import { CompanionScreen } from "./src/features/companion/CompanionScreen";

const tabs = ["伙伴基地", "脑力游乐场", "碰一碰社交", "背包图鉴"] as const;

export default function App() {
  const [server, setServer] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [client, setClient] = useState<TutorClient | null>(null);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [tab, setTab] = useState<(typeof tabs)[number]>(tabs[0]);

  async function connect() {
    setConnecting(true);
    setError("");
    try {
      const next = new TutorClient(serverOrigin(server));
      let authenticated = await next.isAuthenticated();
      if (!authenticated) {
        await next.json("/api/auth/login", post({username, password}));
        authenticated = await next.isAuthenticated();
      }
      if (!authenticated) throw new Error("登录会话尚未建立");
      setPassword("");
      setClient(next);
    } catch (e) {
      setError(String(e));
    } finally {
      setConnecting(false);
    }
  }

  async function disconnect() {
    if (client) await client.fetch("/api/auth/logout", post({})).catch(() => {});
    setTab(tabs[0]);
    setClient(null);
  }

  if (!client) {
    return <SafeAreaView style={styles.frame}>
      <View style={styles.form}>
        <Text style={styles.heading}>DeepTutor 学伴</Text>
        <TextInput style={styles.input} value={server} onChangeText={setServer} autoCapitalize="none" keyboardType="url" placeholder="DeepTutor 服务器地址" placeholderTextColor="#9ca3af" />
        <TextInput style={styles.input} value={username} onChangeText={setUsername} autoCapitalize="none" placeholder="账号" placeholderTextColor="#9ca3af" />
        <TextInput style={styles.input} value={password} onChangeText={setPassword} secureTextEntry placeholder="密码" placeholderTextColor="#9ca3af" />
        <Button title="连接" disabled={connecting || !server.trim()} onPress={() => void connect()} />
        {error ? <Text style={styles.label}>{error}</Text> : null}
      </View>
    </SafeAreaView>;
  }

  return <GestureHandlerRootView style={styles.body}><SafeAreaView style={styles.frame}>
    <View style={styles.body}>
      <View style={[styles.body, tab !== tabs[0] && styles.hidden]}><CompanionScreen client={client} /></View>
      <View style={[styles.body, tab !== tabs[1] && styles.hidden]}><MiniGamesScreen client={client} /></View>
      {tab === tabs[2] && <TradeRoomScreen client={client} />}
      {tab === tabs[3] && <InventoryScreen client={client} />}
    </View>
    <Pressable accessibilityRole="button" onPress={() => void disconnect()} style={{alignSelf: "flex-end", padding: 8}}>
      <Text style={styles.label}>退出账号</Text>
    </Pressable>
    <View accessibilityRole="tablist" style={styles.tabs}>
      {tabs.map(label => <Pressable
        key={label}
        accessibilityRole="tab"
        accessibilityState={{selected: tab === label}}
        onPress={() => setTab(label)}
        style={[styles.tab, tab === label && styles.selected]}
      ><Text style={styles.label}>{label}</Text></Pressable>)}
    </View>
  </SafeAreaView></GestureHandlerRootView>;
}

const styles = StyleSheet.create({
  frame: {flex: 1, backgroundColor: "#101022"},
  body: {flex: 1},
  hidden: {display: "none"},
  form: {padding: 24, gap: 12},
  heading: {color: "#fff", fontWeight: "700", fontSize: 26},
  input: {color: "#fff", padding: 12, borderColor: "#615c8e", borderWidth: 1, borderRadius: 8},
  tabs: {flexDirection: "row", padding: 8, gap: 4, backgroundColor: "#201e37"},
  tab: {flex: 1, alignItems: "center", paddingVertical: 10, borderRadius: 12},
  selected: {backgroundColor: "#45407b"},
  label: {color: "#f3f4ff"},
});
