import React from "react";
import { LiveSurface } from "../live";
import { useApp } from "../state";
export default function Broadcast() {
  const app = useApp();
  return <LiveSurface id={app.session?.player_id || "player-alpha-1"} creator />;
}
