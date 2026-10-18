import React from "react";
import { useLocalSearchParams } from "expo-router";
import { LiveSurface } from "../../live";
export default function Entity() {
  const { id } = useLocalSearchParams<{id:string}>();
  return <LiveSurface id={id || "match-m1"} />;
}
