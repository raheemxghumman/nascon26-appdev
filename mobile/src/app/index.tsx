import React from "react";
import { Redirect } from "expo-router";
import { useApp } from "../state";
import { LoginScreen } from "../screens";
export default function Index() {
  const app = useApp();
  return app.session || app.preview ? (
    <Redirect href="/(tabs)" />
  ) : (
    <LoginScreen />
  );
}
