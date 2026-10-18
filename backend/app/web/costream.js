/* Authenticated host controls. The server enforces ownership and signed invitations. */
let studioSession=location.pathname.split('/')[2]==='costream'?location.pathname.split('/')[3]:null;
let studioSocket,studioHeartbeat;
const studioElement=id=>document.getElementById(id);
function studioAccount(){return window.leagueAccount();}
function studioVisible(){const enabled=!!studioAccount() && (isCreator||isCostream);studioElement('session-panel').hidden=!enabled;if(isCostream&&enabled)studioElement('creator-panel').hidden=false;studioElement('create-session').hidden=!!studioSession;}
function studioMessage(text){studioElement('session-result').textContent=text;}
function studioConnect(){
  if(!studioSession||!studioAccount()?.player_id)return;
  studioSocket?.close();clearInterval(studioHeartbeat);
  studioSocket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/costream/${encodeURIComponent(studioSession)}/${encodeURIComponent(studioAccount().player_id)}?token=${encodeURIComponent(studioAccount().token)}`);
  studioSocket.onopen=()=>{studioHeartbeat=setInterval(()=>{if(studioSocket.readyState===1)studioSocket.send('heartbeat');},1000);};
  studioSocket.onmessage=({data})=>{const state=JSON.parse(data);studioElement('session-state').textContent=`${state.status} · Host: ${state.active_host||'none'} · ${state.active_participants.join(', ')}`;};
  studioSocket.onclose=()=>clearInterval(studioHeartbeat);
}
studioElement('create-session').onclick=async()=>{try{const user=studioAccount();if(!user?.player_id)throw Error('Sign in as a player first.');studioSession=`cs-session-${Date.now()}`;await window.leagueAPI('/api/v1/costream/session',{session_id:studioSession,host_player_id:user.player_id,participants:[user.player_id],layout:'grid_4'},user.token);studioElement('view-session').href='/web/costream/'+studioSession;studioElement('view-session').hidden=false;studioVisible();studioConnect();studioMessage('Co-stream created. Start your camera and invite another player.');}catch(error){studioSession=null;studioMessage(error.message);}};
for(const action of ['invite','mute','unmute','spotlight','kick'])studioElement(action+'-player').onclick=async()=>{try{if(!studioSession)throw Error('Create a co-stream first.');const result=await window.leagueAPI(`/api/v1/costream/${studioSession}/control`,{action,player_id:studioElement('session-player').value.trim()},studioAccount()?.token);if(result.invite_token){studioElement('invite-token').value=result.invite_token;studioMessage('Invitation created. Share this token with the player.');}else studioMessage(`${action} applied.`);}catch(error){studioMessage(error.message);}};
studioElement('accept-invite').onclick=async()=>{try{const token=studioElement('invite-token').value.trim();const payload=JSON.parse(atob(token.split('.')[0].replaceAll('-','+').replaceAll('_','/')));studioSession=payload.session_id;await window.leagueAPI(`/api/v1/costream/${studioSession}/join`,{invite_token:token},studioAccount()?.token);studioConnect();studioMessage('Joined. Start your camera to appear in the broadcast.');studioElement('creator-panel').hidden=false;}catch(error){studioMessage(error.message);}};
async function loadRecordings(){try{const result=await window.leagueAPI('/api/v1/recordings/'+encodeURIComponent(entity));if(!result.recordings.length)return;studioElement('recordings-panel').hidden=false;for(const record of result.recordings){const link=document.createElement('a');link.href=record.playback_url;link.textContent='Play recording · '+record.object.split('/').pop();link.style.display='block';studioElement('recording-links').append(link);}if(path[4]==='vod'){const video=document.getElementById('video');video.src=result.recordings[0].playback_url;video.hidden=false;document.getElementById('video-empty').hidden=true;}}catch{}}
window.addEventListener('league-login',studioVisible);window.addEventListener('league-native-session',studioVisible);studioVisible();loadRecordings();
