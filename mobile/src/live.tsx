import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View, PermissionsAndroid, Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { WebView } from "react-native-webview";
import { useApp } from "./state";
import { Button, color } from "./ui";

export function LiveSurface({ id, creator = false }: { id: string; creator?: boolean }) {
  const app = useApp();
  const web = useRef<WebView>(null);
  const [error, setError] = useState("");
  const [score, setScore] = useState("");
  const [joined, setJoined] = useState(false);
  const [lastMessage, setLastMessage] = useState("");
  const co = id.startsWith("cs-session-");
  const kind = co ? "costream" : id.startsWith("player-") ? "players" : id.startsWith("club-") ? "clubs" : "matches";
  const route = creator ? `/web/creator/${id}` : `/web/${kind}/${id}${kind === "matches" ? "/live" : ""}`;
  const target = app.settings.server.replace(/\/$/, "") + route;
  useEffect(() => {
    if (creator && Platform.OS === "android")
      void PermissionsAndroid.requestMultiple([PermissionsAndroid.PERMISSIONS.CAMERA, PermissionsAndroid.PERMISSIONS.RECORD_AUDIO]);
  }, [creator]);
  useEffect(() => {
    if (!id.startsWith("match-")) return;
    const socket = new WebSocket(app.settings.server.replace(/^http/, "ws") + `/ws/matches/${encodeURIComponent(id)}`);
    socket.onmessage = ({ data }) => {
      try {
        const current = JSON.parse(data);
        setScore(`${current.home.score} - ${current.away.score}`);
      } catch { /* A malformed update does not replace the last good score. */ }
    };
    return () => socket.close();
  }, [app.settings.server, id]);
  useEffect(() => {
    if (!joined) return;
    const socket = new WebSocket(app.settings.server.replace(/^http/, "ws") + `/ws/chat/chat-${encodeURIComponent(id)}`);
    socket.onmessage = ({data}) => {try {setLastMessage(JSON.parse(data).text);} catch { /* Preserve the last valid message. */ }};
    return () => socket.close();
  }, [joined, id, app.settings.server]);
  const injected = app.session ? `sessionStorage.setItem('account', ${JSON.stringify(JSON.stringify(app.session))}); true;` : "true;";
  return (
    <SafeAreaView style={s.page} edges={["top", "left", "right"]}>
      <View style={s.header}>
        <Text style={s.brand}>LEAGUEDESK / LIVE</Text>
        <Text accessibilityRole="header" style={s.heading}>{creator ? "Creator studio" : co ? "Co-stream live" : "Match live"}</Text>
        <Text accessibilityLabel="Live match score" accessibilityLiveRegion="polite" style={s.score}>{score || id}</Text>
        <View style={s.actions}><Button title="‹ Back" secondary onPress={() => router.canGoBack() ? router.back() : router.replace("/")} /><Button title="Scan QR" onPress={() => router.push("/scan")} /><Button title="Settings" secondary onPress={() => router.push("/settings")} /></View>
        {co ? <Button title={joined ? "Joined co-stream" : "Join co-stream"} onPress={() => setJoined(true)} /> : null}
        {lastMessage ? <Text accessibilityLabel="Latest live chat" accessibilityLiveRegion="polite">{lastMessage}</Text> : null}
      </View>
      {error ? <Text style={s.error}>{error}</Text> : null}
      <WebView ref={web} source={{ uri: target }} style={s.web}
        injectedJavaScriptBeforeContentLoaded={injected}
        javaScriptEnabled domStorageEnabled allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction={false} mediaCapturePermissionGrantType="grantIfSameHostElseDeny"
        mixedContentMode="compatibility" startInLoadingState
        renderLoading={() => <ActivityIndicator color={color.green} />}
        onError={(event) => setError(event.nativeEvent.description)}
        onShouldStartLoadWithRequest={(request) => !request.url.startsWith("nascon:")}
      />
    </SafeAreaView>
  );
}
const s = StyleSheet.create({page:{flex:1,backgroundColor:color.paper},header:{padding:16,gap:7,backgroundColor:color.paper},brand:{fontSize:11,fontWeight:"800",letterSpacing:2,color:color.green},heading:{fontSize:26,fontWeight:"800",color:color.ink},score:{fontSize:18,fontWeight:"700",color:color.ink},actions:{flexDirection:"row",gap:8,flexWrap:"wrap"},web:{flex:1},error:{color:color.red,padding:12}});
