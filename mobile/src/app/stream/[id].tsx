import React from "react";
import { useLocalSearchParams } from "expo-router";
import { LiveSurface } from "../../live";
export default function Stream() {
  const { id } = useLocalSearchParams<{id:string}>();
  return <LiveSurface id={id || "cs-session-101"} />;
}
