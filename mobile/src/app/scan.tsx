import React, { useState } from "react";
import { Text, View } from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { router } from "expo-router";
import { Button, Page, Notice } from "../ui";
import { useApp } from "../state";

export default function Scan() {
  const [permission, requestPermission] = useCameraPermissions();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const app = useApp();
  const scan = async (data: string) => {
    if (busy) return;
    setBusy(true);setError("");
    try {
      const url = new URL(data);
      if (url.protocol === "nascon:" && ["entity", "stream"].includes(url.hostname)) {
        const id = url.pathname.split("/").filter(Boolean)[0];
        if (!id || !/^[a-zA-Z0-9_.:-]{1,80}$/.test(id)) throw new Error("Invalid entity identifier.");
        router.replace({pathname: url.hostname === "stream" ? "/stream/[id]" : "/entity/[id]",params:{id}});
      } else {
        const code = url.pathname.match(/^\/q\/([a-zA-Z0-9_-]+)$/)?.[1];
        if (!code) throw new Error("Scan a LeagueDesk match, player, club or stream QR code.");
        const response = await fetch(app.settings.server + "/q/" + code);
        if (!response.ok) throw new Error("This QR code is unavailable.");
        const entity = new URL(response.url).pathname.split("/")[3];
        if (!entity) throw new Error("The QR code did not resolve to an entity.");
        router.replace({pathname: entity.startsWith("cs-session-") ? "/stream/[id]" : "/entity/[id]",params:{id:entity}});
      }
    } catch (err) {setError(err instanceof Error ? err.message : String(err));setBusy(false);}
  };
  return <Page title="Scan to watch" subtitle="Point your camera at a LeagueDesk QR code." back>
    {!permission?.granted ? <Button title="Allow camera" onPress={() => void requestPermission()} /> :
      <View style={{height:380,borderRadius:18,overflow:"hidden"}}><CameraView style={{flex:1}} barcodeScannerSettings={{barcodeTypes:["qr"]}} onBarcodeScanned={busy?undefined:({data})=>void scan(data)} /></View>}
    {error ? <Notice text={error} /> : null}
    {busy ? <Text>Opening your match…</Text> : null}
  </Page>;
}
