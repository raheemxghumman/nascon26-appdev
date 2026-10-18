import React from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { useApp } from "./state";

export const color = {
  ink: "#102A28",
  muted: "#60736E",
  green: "#14634F",
  lime: "#DDF594",
  paper: "#F5F6F0",
  line: "#DAE2D8",
  white: "#FFFFFF",
  red: "#9E352F",
};
export const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: color.paper },
  header: {
    backgroundColor: color.ink,
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 16,
  },
  brand: {
    color: color.lime,
    fontWeight: "800",
    fontSize: 12,
    letterSpacing: 3,
  },
  title: {
    fontSize: 30,
    fontWeight: "800",
    color: color.ink,
    letterSpacing: -1,
  },
  subtitle: { fontSize: 14, color: color.muted, lineHeight: 21 },
  body: { padding: 20, paddingBottom: 36, gap: 16 },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  spread: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
  card: {
    backgroundColor: color.white,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: 18,
    padding: 18,
    gap: 12,
  },
  label: {
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1.5,
    color: color.muted,
    textTransform: "uppercase",
  },
  h2: { fontSize: 19, fontWeight: "700", color: color.ink },
  text: { fontSize: 15, lineHeight: 23, color: color.ink },
  button: {
    minHeight: 48,
    borderRadius: 12,
    backgroundColor: color.green,
    paddingHorizontal: 16,
    paddingVertical: 13,
    justifyContent: "center",
    alignItems: "center",
  },
  buttonText: { fontSize: 15, fontWeight: "700", color: color.white },
  secondary: {
    backgroundColor: "#E9EFE5",
    borderWidth: 1,
    borderColor: color.line,
  },
  input: {
    minHeight: 50,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: 11,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    backgroundColor: color.white,
    color: color.ink,
  },
  notice: { backgroundColor: "#FFF2D5", padding: 12, borderRadius: 10 },
  score: { fontSize: 44, fontWeight: "800", color: color.ink },
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 7,
    backgroundColor: color.lime,
  },
  badgeText: { fontSize: 11, fontWeight: "800", color: color.ink },
  team: { fontSize: 17, fontWeight: "700", color: color.ink, flex: 1 },
  line: { height: 1, backgroundColor: color.line },
  hero: { backgroundColor: color.ink, borderRadius: 20, padding: 22, gap: 16 },
  heroTitle: {
    fontSize: 31,
    lineHeight: 36,
    fontWeight: "800",
    color: color.white,
  },
  heroText: { color: "#C5D8D0", fontSize: 14, lineHeight: 21 },
  error: { color: color.red, fontSize: 14, lineHeight: 20 },
  stat: {
    flex: 1,
    backgroundColor: "#EDF2E7",
    padding: 14,
    borderRadius: 12,
    gap: 4,
  },
  statNumber: { fontSize: 24, fontWeight: "800", color: color.ink },
  preview: { backgroundColor: "#F4DDB5", padding: 10 },
  chip: {
    minHeight: 48,
    padding: 12,
    borderRadius: 10,
    backgroundColor: color.white,
    borderWidth: 1,
    borderColor: color.line,
    justifyContent: "center",
  },
  chipSelected: { backgroundColor: color.lime, borderColor: color.green },
  small: { fontSize: 12, color: color.muted, lineHeight: 18 },
  empty: { paddingVertical: 20, gap: 8 },
  field: { gap: 7 },
  link: { color: color.green, fontSize: 14, fontWeight: "700" },
  circle: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: color.lime,
    alignItems: "center",
    justifyContent: "center",
  },
  circleText: { fontWeight: "800", fontSize: 15, color: color.ink },
});
export function Button({
  title,
  onPress,
  secondary = false,
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  secondary?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.button,
        secondary && styles.secondary,
        disabled && { opacity: 0.5 },
      ]}
    >
      <Text style={[styles.buttonText, secondary && { color: color.ink }]}>
        {title}
      </Text>
    </Pressable>
  );
}
export function Field({
  label,
  value,
  onChangeText,
  secret = false,
  placeholder = "",
  numeric = false,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  secret?: boolean;
  placeholder?: string;
  numeric?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        secureTextEntry={secret}
        placeholder={placeholder}
        placeholderTextColor={color.muted}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType={numeric ? "number-pad" : "default"}
      />
    </View>
  );
}
export function Page({
  title,
  subtitle,
  children,
  back = false,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  back?: boolean;
}) {
  const app = useApp(),
    pending = app.actions.filter((a) => a.state === "pending").length;
  return (
    <SafeAreaView edges={["top", "left", "right"]} style={styles.page}>
      <View style={styles.header}>
        <View style={styles.spread}>
          <Text style={styles.brand}>LEAGUEDESK / NASCON 26</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Server settings"
            onPress={() => router.push("/settings")}
            style={{ minHeight: 44, justifyContent: "center" }}
          >
            <Text style={{ color: color.white, fontWeight: "700" }}>
              Settings
            </Text>
          </Pressable>
        </View>
        <View style={styles.spread}>
          <Text
            accessibilityLiveRegion="polite"
            style={{
              color: app.online ? color.lime : "#FFD39A",
              fontSize: 12,
              fontWeight: "700",
            }}
          >
            {app.syncing ? "↻ Syncing" : app.online ? "● Online" : "○ Offline"}
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push("/(tabs)/sync")}
          >
            <Text style={{ color: "#D3E2D9", fontSize: 12 }}>
              {pending} pending actions
            </Text>
          </Pressable>
        </View>
      </View>
      {app.preview && (
        <View style={styles.preview}>
          <Text style={{ fontSize: 12, fontWeight: "700", color: color.ink }}>
            READ-ONLY PREVIEW · Sample data, not connected results
          </Text>
        </View>
      )}
      <View style={{flexDirection:"row",paddingHorizontal:16,paddingTop:10,gap:10}}>
        <Button title="Watch live" secondary onPress={() => router.push("/entity/match-m1")} />
        <Button title="Scan QR" secondary onPress={() => router.push("/scan")} />
        <Button title="Broadcast" secondary onPress={() => router.push("/broadcast")} />
      </View>
      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
      >
        {back && (
          <Button
            title="‹ Back"
            secondary
            onPress={() =>
              router.canGoBack() ? router.back() : router.replace("/(tabs)")
            }
          />
        )}
        <View style={{ gap: 6 }}>
          <Text accessibilityRole="header" style={styles.title}>
            {title}
          </Text>
          {subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
        </View>
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}
export function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.h2}>{title}</Text>
      <Text style={styles.subtitle}>{detail}</Text>
    </View>
  );
}
export function Notice({ text }: { text: string }) {
  return (
    <View style={styles.notice}>
      <Text style={styles.text}>{text}</Text>
    </View>
  );
}
export function Busy() {
  return <ActivityIndicator size="small" color={color.green} />;
}
export function Badge({ text }: { text: string }) {
  return (
    <View style={styles.badge}>
      <Text style={styles.badgeText}>
        {text.replaceAll("_", " ").toUpperCase()}
      </Text>
    </View>
  );
}
