import React, { useEffect, useRef, useState } from "react";
import { Stack, router } from "expo-router";
import { ActivityIndicator, View, Text, Pressable } from "react-native";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AppProvider, useApp } from "../state";
import { color } from "../ui";

function Navigation() {
  const { ready, session, settings } = useApp();
  const [notice,setNotice] = useState<{type:string;match_id?:string;session_id?:string}|null>(null);
  const lastEvent = useRef<string|undefined>(undefined);
  useEffect(() => {
    if (!ready || !session) return;
    let active=true, socket:WebSocket, timer:ReturnType<typeof setTimeout>;
    const connect=()=>{
      socket=new WebSocket(settings.server.replace(/^http/,"ws")+"/ws/notifications");
      socket.onopen=()=>socket.send(JSON.stringify({token:session.token,last_event_id:lastEvent.current}));
      socket.onmessage=({data})=>{try{const event=JSON.parse(data);lastEvent.current=event.event_id;setNotice(event);}catch{/* Ignore malformed notifications. */}};
      socket.onclose=(event)=>{if(active && event.code!==1008)timer=setTimeout(connect,1500);};
    };
    connect();
    return()=>{active=false;clearTimeout(timer);socket?.close();};
  },[ready,session,settings.server]);
  if (!ready)
    return (
      <View
        style={{
          flex: 1,
          justifyContent: "center",
          backgroundColor: color.paper,
        }}
      >
        <ActivityIndicator color={color.green} />
      </View>
    );
  return (
    <>
      <StatusBar style="light" />
      {notice ? <View accessibilityRole="alert" style={{backgroundColor:color.lime,padding:12,flexDirection:"row",justifyContent:"space-between",gap:10}}><Pressable style={{flex:1,minHeight:48,justifyContent:"center"}} onPress={()=>{if(notice.session_id)router.push({pathname:"/stream/[id]",params:{id:notice.session_id}});else if(notice.match_id)router.push({pathname:"/entity/[id]",params:{id:notice.match_id}});setNotice(null);}}><Text style={{color:color.ink,fontWeight:"700"}}>{notice.type==="match.event"?"Match score updated":notice.type==="costream.invite"?"You have a co-stream invitation":"Your order status changed"}</Text></Pressable><Pressable accessibilityLabel="Dismiss notification" style={{minHeight:48,minWidth:48,justifyContent:"center"}} onPress={()=>setNotice(null)}><Text>Dismiss</Text></Pressable></View> : null}
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: color.paper },
        }}
      />
    </>
  );
}
export default function Layout() {
  return (
    <SafeAreaProvider>
      <AppProvider>
        <Navigation />
      </AppProvider>
    </SafeAreaProvider>
  );
}
