/* Guest access never opens an auth wall until the visitor requests a protected action. */
const $ = s => document.querySelector(s);
const path = location.pathname.split('/');
const entity = path[3] || 'match-m1';
const isMatch = path[2] === 'matches';
const isCreator = path[2] === 'creator';
const isCostream = path[2] === 'costream';
// A creator broadcasts into a match: share its chat room and QR with the viewers of that match.
const matchEntity = isCreator ? (new URLSearchParams(location.search).get('match') || 'match-m1') : entity;
const room = `chat-${matchEntity}`;
let guestToken = sessionStorage.getItem('guestToken');
let account = JSON.parse(sessionStorage.getItem('account') || 'null');
let cart = JSON.parse(sessionStorage.getItem('guestCart') || '[]');
let pendingAction = null;
const modal = $('[data-testid="progressive-auth-modal"]');
async function api(url, body, token) {
  const response = await fetch(url, {method: body === undefined ? 'GET' : 'POST', headers: {'Content-Type':'application/json', ...(token ? {Authorization:`Bearer ${token}`} : {})}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  const data = await response.json();
  if(!response.ok) {const error = new Error(data.error?.message || 'Request failed'); error.status = response.status; throw error;}
  return data;
}
window.leagueAPI = api;
window.leagueAccount = () => account;
window.addEventListener('league-native-session',()=>{account=JSON.parse(sessionStorage.getItem('account')||'null');});
function updateCart(){ const count = cart.reduce((n,i)=>n+i.quantity,0); $('[data-testid="guest-cart-count"]').textContent=count; $('#bag-detail').textContent=count?`${count} × Alpha Home Jersey · Size L`:'Pick something from the club shop.'; sessionStorage.setItem('guestCart',JSON.stringify(cart)); }
updateCart();
async function ensureGuest(){if(!guestToken){const data=await api('/api/v1/guest/session',{});guestToken=data.guest_token;sessionStorage.setItem('guestToken',guestToken);}return guestToken;}
function authPrompt(action){ pendingAction=action; sessionStorage.setItem('playbackTime',String($('#video').currentTime||0)); modal.showModal(); }
window.leagueAuthPrompt=authPrompt;
$('#close-auth').onclick=()=>modal.close();
$('[data-testid="add-to-guest-cart-btn"]').onclick=()=>{let item=cart.find(i=>i.variant_id==='var-jersey-001-L');if(item)item.quantity++;else cart.push({variant_id:'var-jersey-001-L',quantity:1});updateCart();ensureGuest().catch(showError);};
$('#checkout').onclick=()=>{if(!cart.length){$('#notice').textContent='Add an item to your bag first.';return;}if(!account)authPrompt('checkout');else mergeCart().catch(showError);};
async function mergeCart(){if(!cart.length)return;const token=await ensureGuest();const result=await api('/api/v1/guest/cart-merge',{guest_token:token,registered_user_id:account.player_id||account.user_id,guest_cart:cart,test_write_block:true},account.token);const items=cart.map(i=>({variant_id:i.variant_id,quantity:i.quantity}));cart=[];updateCart();sessionStorage.removeItem('guestToken');guestToken=null;$('#bag-detail').textContent=`Bag moved to your account (${result.active_cart.total_items} item(s)). Completing your order…`;try{const order=await api('/audit/v1/checkout',{order_id:'web-'+Date.now().toString(36),customer_id:account.user_id||account.player_id||'member',items,discount_code:null,payment:{token:'tok_success'}},account.token);$('#bag-detail').textContent=`Order paid: PKR ${(order.total_minor/100).toFixed(2)} (${order.order_id}).`;if(order.receipt&&order.receipt.pdf_base64){const a=document.createElement('a');a.href='data:application/pdf;base64,'+order.receipt.pdf_base64;a.download=`receipt-${order.order_id}.pdf`;a.textContent='Download receipt (PDF)';$('#bag-detail').append(document.createElement('br'),a);}}catch(error){$('#bag-detail').textContent=`Your bag is saved to your account, but the payment did not go through: ${error.message||error}`;}return result;}
$('#auth-form').onsubmit=async event=>{event.preventDefault();$('#auth-error').textContent='';try{account=await api('/api/v1/auth/login',{email:$('#email').value,password:$('#password').value});sessionStorage.setItem('account',JSON.stringify(account));if(cart.length)await mergeCart();modal.close();const time=Number(sessionStorage.getItem('playbackTime')||0);if(Number.isFinite($('#video').duration))$('#video').currentTime=time;if(pendingAction==='chat')await sendChat();window.dispatchEvent(new Event('league-login'));}catch(error){$('#auth-error').textContent=error.message;}};
function showError(error){$('#notice').textContent=error.message;}
async function sendChat(){const text=$('[data-testid="chat-input-field"]').value.trim();if(!text)return;try{const result=await api('/api/v1/chat',{chat_room_id:room,text,message_id:crypto.randomUUID?.()||`msg-${Date.now()}`},account?.token||await ensureGuest());if(result.filtered_messages.length)$('[data-testid="chat-input-field"]').value='';else $('#notice').textContent='This message was blocked by moderation.';}catch(error){if(error.status===403&&!account)authPrompt('chat');else showError(error);}}
$('#chat-form').onsubmit=event=>{event.preventDefault();sendChat();};
let scoreSocket,chatSocket;
function connectScore(){if(!isMatch&&!isCreator)return;scoreSocket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/matches/${encodeURIComponent(matchEntity)}`);scoreSocket.onmessage=event=>{const s=JSON.parse(event.data);$('[data-testid="live-score-banner"]').textContent=`${s.home.score} - ${s.away.score}`;$('#connection').textContent='Live updates';$('#match-status').textContent=s.status.replaceAll('_',' ').toUpperCase();};scoreSocket.onclose=()=>{$('#connection').textContent='Reconnecting';setTimeout(connectScore,1000);};}
let seen=new Set();
function connectChat(){chatSocket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/chat/${encodeURIComponent(room)}`);chatSocket.onmessage=event=>{const m=JSON.parse(event.data);if(seen.has(m.sequence))return;seen.add(m.sequence);const p=document.createElement('p');const name=document.createElement('strong');name.textContent=m.sender+': ';p.append(name,document.createTextNode(m.text));$('[data-testid="chat-message-list"]').append(p);p.scrollIntoView({block:'nearest'});};chatSocket.onclose=()=>setTimeout(connectChat,1000);}
let activeMediaPath=null;
async function loadMedia(){if(path[4]==='vod')return;try{const data=await api(`/api/v1/live/${encodeURIComponent(entity)}`);if(data.path&&data.path!==activeMediaPath){activeMediaPath=data.path;$('#webrtc').src=`/media/read/${data.path}?autoplay=true&muted=true`;$('#webrtc').hidden=false;$('#video-empty').hidden=true;}else if(!data.path){activeMediaPath=null;$('#webrtc').src='about:blank';$('#webrtc').hidden=true;$('#video-empty').hidden=false;}}catch{activeMediaPath=null;$('#webrtc').src='about:blank';$('#webrtc').hidden=true;$('#video-empty').hidden=false;} }
async function start(){
  await ensureGuest();
  if(isCreator){$('#creator-panel').hidden=false;$('#title').textContent='Your club. Your broadcast.';$('#subtitle').textContent='Go live from your camera, or connect an external encoder.';$('#teams').textContent='Creator studio';}
  else if(isCostream){$('#title').textContent='Together, live.';$('#subtitle').textContent='One broadcast. One conversation.';$('#teams').textContent='Co-stream session';}
  else if(isMatch){$('#title').textContent='Alpha United vs Alpha Rovers';$('#subtitle').textContent='Football · Alpha Stadium, Islamabad';if(path[4]==='vod')$('#video-message').textContent='Match complete · recordings';if(path[4]==='notice')$('#video-message').textContent='Match '+new URLSearchParams(location.search).get('state');}
  else{$('#title').textContent=entity.replaceAll('-',' ');$('#teams').textContent='Club community';}
  $('#app-link').href=`nascon://${isCostream?'stream':'entity'}/${encodeURIComponent(entity)}`;
  {const qrBase=`/audit/v1/qr/${encodeURIComponent(matchEntity)}/export`;$('#qr').src=qrBase+'.png';for(const fmt of ['svg','png','pdf']){const link=$('#qr-'+fmt);link.href=`${qrBase}.${fmt}`;link.setAttribute('download',`${matchEntity}-qr.${fmt}`);link.setAttribute('rel','noopener');}}
  connectScore();connectChat();await loadMedia();setInterval(loadMedia,2000);
}
start().catch(showError);
