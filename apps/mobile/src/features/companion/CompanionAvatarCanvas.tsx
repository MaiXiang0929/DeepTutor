import { useEffect } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { RiveView, useRiveBoolean, useRiveFile, useRiveNumber, useRiveTrigger, useViewModelInstance } from "@rive-app/react-native";
import { ImpactFeedbackStyle, impactAsync } from "expo-haptics";
import type { EmotionState } from "@deeptutor/shared-protocol";
import { emotionInputs } from "./emotions";

type Props = { emotion: EmotionState; speaking: boolean };
const fallback = {idle: "◉", happy: "✦", proud: "★", empathetic: "♡", thinking: "◎", excited: "✹"};

export function CompanionAvatarCanvas({emotion, speaking}: Props) {
  const {riveFile} = useRiveFile(process.env.EXPO_PUBLIC_COMPANION_RIVE_URL);
  const {instance} = useViewModelInstance(riveFile, {async: true});
  const {setValue: setEmotion} = useRiveNumber("emotion_state", instance);
  const {setValue: setSpeaking} = useRiveBoolean("is_speaking", instance);
  const {trigger: pat} = useRiveTrigger("on_head_pat", instance);
  const {trigger: poke} = useRiveTrigger("on_poke", instance);

  useEffect(() => { setEmotion(emotionInputs[emotion]); }, [emotion, setEmotion]);
  useEffect(() => { setSpeaking(speaking); }, [speaking, setSpeaking]);

  function touch(action: () => void) {
    action();
    void impactAsync(ImpactFeedbackStyle.Light).catch(() => {});
  }

  return (
    <View style={styles.panel}>
      {riveFile && instance ? (
        <RiveView file={riveFile} dataBind={instance} style={styles.canvas} />
      ) : <Text accessibilityLabel={emotion} style={styles.avatar}>{fallback[emotion]}</Text>}
      <Pressable accessibilityRole="button" accessibilityLabel="摸摸头" style={styles.head} onPress={() => touch(pat)} />
      <Pressable accessibilityRole="button" accessibilityLabel="戳一戳" style={styles.body} onPress={() => touch(poke)} />
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {height: 220, alignItems: "center", justifyContent: "center", backgroundColor: "#211d43", borderRadius: 24, overflow: "hidden"},
  canvas: {width: "100%", height: "100%"},
  avatar: {fontSize: 100, color: "#a5b4fc"},
  head: {position: "absolute", top: 0, bottom: "50%", left: 0, right: 0},
  body: {position: "absolute", top: "50%", bottom: 0, left: 0, right: 0},
});
