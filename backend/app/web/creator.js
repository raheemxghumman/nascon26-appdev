/* Browser/WebView WHIP publisher. Camera bytes go to the self-hosted MediaMTX server. */
let peer, camera, keyRecord;
document.querySelector('#creator-login').onclick=()=>window.leagueAuthPrompt('broadcast');
document.querySelector('#start-broadcast').onclick=async()=>{
  const message=document.querySelector('#broadcast-status');
  try{
    const user=window.leagueAccount();if(!user){window.leagueAuthPrompt('broadcast');return;}
    if(!user.player_id && user.role!=='super_admin'){throw new Error('Sign in with a player account to broadcast.');}
    const pid=user.player_id||'player-alpha-1';
    keyRecord=await window.leagueAPI('/api/v1/creator/key',{action:'generate',player_id:pid,label:'Native camera'},user.token);
    try{camera=await navigator.mediaDevices.getUserMedia({video:{width:640,height:360,frameRate:24},audio:true});}
    catch(error){if(error.name!=='NotReadableError'&&error.name!=='AbortError')throw error;camera=await navigator.mediaDevices.getUserMedia({video:{width:640,height:360,frameRate:24},audio:false});}
    document.querySelector('#camera-preview').srcObject=camera;
    peer=new RTCPeerConnection();camera.getTracks().forEach(track=>peer.addTrack(track,camera));
    // Prefer H264 so the same camera broadcast can also be packaged for HLS.
    for(const transceiver of peer.getTransceivers())if(transceiver.sender.track?.kind==='video'&&transceiver.setCodecPreferences){const codecs=RTCRtpSender.getCapabilities('video')?.codecs||[];transceiver.setCodecPreferences([...codecs.filter(c=>c.mimeType==='video/H264'),...codecs.filter(c=>c.mimeType!=='video/H264')]);}
    await peer.setLocalDescription(await peer.createOffer());
    await new Promise(resolve=>{if(peer.iceGatheringState==='complete')resolve();else{const timer=setTimeout(resolve,3000);peer.onicegatheringstatechange=()=>{if(peer.iceGatheringState==='complete'){clearTimeout(timer);resolve();}};}});
    const response=await fetch(`/api/v1/media/whip/live/${keyRecord.stream_key}`,{method:'POST',headers:{'Content-Type':'application/sdp',Authorization:`Bearer ${user.token}`},body:peer.localDescription.sdp});
    if(!response.ok)throw new Error('Media server could not start the broadcast.');
    await peer.setRemoteDescription({type:'answer',sdp:await response.text()});
    message.textContent=camera.getAudioTracks().length?'You are live. Camera and microphone are broadcasting.':'You are live. Camera is broadcasting; the microphone is unavailable on this device.';
    document.querySelector('#stop-broadcast').disabled=false;document.querySelector('#start-broadcast').disabled=true;
  }catch(error){message.textContent=error.message;if(peer)peer.close();if(camera)camera.getTracks().forEach(t=>t.stop());}
};
document.querySelector('#stop-broadcast').onclick=async()=>{
  const user=window.leagueAccount();if(peer)peer.close();if(camera)camera.getTracks().forEach(t=>t.stop());
  try{if(keyRecord)await window.leagueAPI('/api/v1/creator/key',{action:'revoke',player_id:keyRecord.player_id},user.token);}catch(error){document.querySelector('#broadcast-status').textContent=error.message;return;}
  document.querySelector('#broadcast-status').textContent='Broadcast ended.';document.querySelector('#start-broadcast').disabled=false;document.querySelector('#stop-broadcast').disabled=true;
};
