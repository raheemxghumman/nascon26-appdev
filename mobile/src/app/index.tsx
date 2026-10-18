import React from "react";
import { Redirect } from "expo-router";
import { useApp } from "../state";
// "/" is shared with (tabs)/index, so the entry point always redirects to an explicit route.
export default function Index() {
  const app = useApp();
  return <Redirect href={app.session || app.preview ? "/(tabs)" : "/login"} />;
}
