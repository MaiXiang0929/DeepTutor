import { useEffect, useState } from "react";
import { Button, Pressable, ScrollView, Text, View } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import type { InventoryItem, ItemCategory, Subject, UserGameProfile } from "@deeptutor/shared-protocol";
import { post, type TutorClient } from "../../client";
import { SynthesisCanvas } from "./SynthesisCanvas";

type CatalogItem = {item_id: string; name: string; category: ItemCategory; subject_tag: Subject; synthesis_recipe_json: string[]};
const SUBJECTS = {math: "数学", physics: "物理", literature: "文学", history: "历史", coding: "编程"};
const RARITY = {common: "#cbd5e1", rare: "#7dd3fc", epic: "#c4b5fd", legendary: "#fcd34d"};
const ROOT = "/api/v1/gamification";
const text = {color: "#e0e7ff"};

function Fragment({item, choose}: {item: InventoryItem; choose: () => void}) {
  const drag = Gesture.Pan().runOnJS(true).onEnd(event => {
    if (event.translationY < -25) choose();
  });
  return <GestureDetector gesture={drag}>
    <Pressable onPress={choose} accessibilityRole="button" style={{padding: 10, borderWidth: 1, borderRadius: 12, borderColor: RARITY[item.rarity]}}>
      <Text style={{color: RARITY[item.rarity]}}>{item.name} ×{item.quantity}</Text>
    </Pressable>
  </GestureDetector>;
}

export function InventoryScreen({client}: {client: TutorClient}) {
  const [profile, setProfile] = useState<UserGameProfile | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [slots, setSlots] = useState<InventoryItem[]>([]);
  const [effect, setEffect] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const options = {signal: controller.signal};
    void Promise.all([
      client.json<UserGameProfile>(ROOT + "/profile", options),
      client.json<CatalogItem[]>(ROOT + "/catalog", options),
    ]).then(([next, items]) => {
      if (!controller.signal.aborted) {
        setProfile(next);
        setCatalog(items);
      }
    }).catch(e => { if (!controller.signal.aborted) setMessage(String(e)); });
    return () => controller.abort();
  }, [client]);

  const recipe = catalog.find(item =>
    item.synthesis_recipe_json.length === 3 && slots.length === 3 &&
    item.synthesis_recipe_json.every(id => slots.some(slot => slot.item_id === id))
  );
  const owned = new Set(profile?.inventory.map(item => item.item_id));
  const missing = catalog.find(item => item.synthesis_recipe_json.length === 3)?.synthesis_recipe_json
    .map(id => catalog.find(item => item.item_id === id))
    .find(item => item && !owned.has(item.item_id));

  async function synthesize() {
    if (!recipe || busy) return;
    setBusy(true);
    try {
      setProfile(await client.json(ROOT + "/synthesize", post({target_item_id: recipe.item_id})));
      setSlots([]);
      setEffect(n => n + 1);
      setMessage(`解锁 ${recipe.name}`);
    } catch (e) {
      setMessage(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function equip(item: InventoryItem) {
    setBusy(true);
    try {
      setProfile(await client.json(ROOT + "/equip", post({item_id: item.item_id, equipped: !item.is_equipped})));
    } catch (e) {
      setMessage(String(e));
    } finally {
      setBusy(false);
    }
  }

  return <ScrollView contentContainerStyle={{padding: 18, gap: 14}}>
    <Text style={[text, {fontSize: 26, fontWeight: "700"}]}>背包图鉴</Text>
    <SynthesisCanvas run={effect} />
    <Text style={text}>将三种不同学科碎片向上拖入合成槽，也可直接点选。</Text>
    <View style={{flexDirection: "row", flexWrap: "wrap", gap: 8}}>
      {[0, 1, 2].map(index => <Button key={index} title={slots[index]?.name ?? "空槽"} onPress={() => setSlots(values => values.filter((_, i) => i !== index))} />)}
    </View>
    <Button title={recipe ? `合成 ${recipe.name}` : "合成"} disabled={busy || !recipe} onPress={() => void synthesize()} />
    {missing && <Text style={text}>缺少{SUBJECTS[missing.subject_tag]}碎片，可和同学碰一碰交换。</Text>}
    {Object.entries(SUBJECTS).map(([subject, name]) => <View key={subject} style={{gap: 8}}>
      <Text style={text}>{name}</Text>
      {profile?.inventory.filter(item => item.subject_tag === subject).map(item => (
        item.category === "card_fragment"
          ? <Fragment key={item.id} item={item} choose={() => setSlots(previous =>
            previous.length < 3 && !previous.some(slot => slot.subject_tag === item.subject_tag) ? [...previous, item] : previous
          )} />
          : <Button key={item.id} title={`${item.name}${item.is_equipped ? " · 已穿戴" : ""}`} disabled={busy || item.category === "badge"} onPress={() => void equip(item)} />
      ))}
    </View>)}
    {message ? <Text accessibilityRole="alert" style={text}>{message}</Text> : null}
  </ScrollView>;
}
