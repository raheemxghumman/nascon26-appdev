import React from "react";
import { Tabs, Redirect } from "expo-router";
import { Text } from "react-native";
import { useApp } from "../../state";
import { color } from "../../ui";
const ICONS: Record<string, string> = {
  index: "🏠",
  fixtures: "📅",
  standings: "🏆",
  club: "🛡️",
  store: "🛍️",
  sync: "🔄",
};
export default function TabLayout() {
  const app = useApp();
  if (!app.session && !app.preview) return <Redirect href="/login" />;
  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: color.green,
        tabBarInactiveTintColor: color.muted,
        tabBarStyle: {
          backgroundColor: color.white,
          borderTopColor: color.line,
          height: 64,
          paddingBottom: 8,
          paddingTop: 6,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "700" },
        tabBarIcon: ({ focused }) => (
          <Text
            accessibilityElementsHidden
            importantForAccessibility="no"
            style={{ fontSize: 20, opacity: focused ? 1 : 0.55 }}
          >
            {ICONS[route.name] ?? "•"}
          </Text>
        ),
      })}
    >
      <Tabs.Screen name="index" options={{ title: "Home" }} />
      <Tabs.Screen name="fixtures" options={{ title: "Fixtures" }} />
      <Tabs.Screen name="standings" options={{ title: "Table" }} />
      <Tabs.Screen name="club" options={{ title: "Club" }} />
      <Tabs.Screen name="store" options={{ title: "Shop" }} />
      <Tabs.Screen name="sync" options={{ title: "Sync" }} />
    </Tabs>
  );
}
