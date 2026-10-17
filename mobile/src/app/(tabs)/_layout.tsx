import React from "react";
import { Tabs, Redirect } from "expo-router";
import { Text } from "react-native";
import { useApp } from "../../state";
import { color } from "../../ui";
export default function TabLayout() {
  const app = useApp();
  if (!app.session && !app.preview) return <Redirect href="/" />;
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: color.green,
        tabBarInactiveTintColor: color.muted,
        tabBarStyle: {
          backgroundColor: color.white,
          borderTopColor: color.line,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "700" },
        tabBarIcon: ({ focused }) => (
          <Text
            style={{ fontSize: 16, color: focused ? color.green : color.muted }}
          >
            {focused ? "●" : "○"}
          </Text>
        ),
      }}
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
