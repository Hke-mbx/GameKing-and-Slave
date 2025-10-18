// server.js
require('dotenv').config();
const express = require('express');
const http = require('http');
const { nanoid } = require('nanoid');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

const server = http.createServer(app);
const io = require('socket.io')(server, {
  cors: { origin: process.env.CORS_ORIGIN || "*" }
});

// --- In-memory stores (MVP) ---
const users = {};   // userId -> { id, name, socketId, wins, losses, preferred }
const sockets = {}; // socketId -> userId
const rooms = {};   // roomId -> { id, hostId, players:[], opening: {userId:opening}, hands:{userId:[]}, played:{userId:card}, discards:{userId:[]}, state }

// --- Card templates (same as front-end) ---
const templates = {
  king: [
    { name:'市民', tag:'citizen', lvl:1 },
    { name:'市民', tag:'citizen', lvl:1 },
    { name:'刺客', tag:'assassin', lvl:2 },
    { name:'屠夫', tag:'butcher', lvl:2 },
    { name:'皇家守卫', tag:'royalguard', lvl:2 },
    { name:'国王', tag:'king', lvl:3 }
  ],
  queen: [
    { name:'市民', tag:'citizen', lvl:1 },
    { name:'市民', tag:'citizen', lvl:1 },
    { name:'刺客', tag:'assassin', lvl:2 },
    { name:'屠夫', tag:'butcher', lvl:2 },
    { name:'终极守卫', tag:'ultguard', lvl:3 },
    { name:'女王', tag:'queen', lvl:3 }
  ],
  slave: [
    { name:'奴隶', tag:'slave', lvl:0 },
    { name:'奴隶', tag:'slave', lvl:0 },
    { name:'市民', tag:'citizen', lvl:1 },
    { name:'市民', tag:'citizen', lvl:1 },
    { name:'守卫', tag:'guard', lvl:2 },
    { name:'刺客', tag:'assassin', lvl:2 },
    { name:'屠夫', tag:'butcher', lvl:2 }
  ]
};

function cloneDeck(opening){
  const src = templates[opening] || templates['slave'];
  // deep clone & add uid
  return shuffle(src.map(c=> ({ ...JSON.parse(JSON.stringify(c)), _id: nanoid(8) })));
}
function shuffle(a){ for(let i=a.length-1;i>0;i--){ const j=Math.floor(Math.random()*(i+1)); [a[i],a[j]]=[a[j],a[i]] } return a; }

// ---------- utilities ----------
function makeUser(name){
  const id = nanoid(8);
  users[id] = { id, name: name || `玩家_${Math.floor(Math.random()*900)}`, socketId: null, wins:0, losses:0, preferred:'slave' };
  return users[id];
}
function publicUsers(){ return Object.values(users).map(u=>({ id:u.id, name:u.name, online: !!u.socketId, wins:u.wins, losses:u.losses })); }
function summarizeRoom(roomId){
  const r = rooms[roomId];
  if(!r) return null;
  return {
    id: r.id,
    hostId: r.hostId,
    players: r.players.map(pid=>({ id: pid, name: users[pid] ? users[pid].name : pid })),
    state: r.state || 'waiting',
    openings: r.opening || {}
  };
}

// ---------- socket handlers ----------
io.on('connection', socket => {
  console.log('socket connected', socket.id);

  // register / reconnect: payload { userId?, name? }
  socket.on('register', (payload, cb) => {
    try {
      let u;
      if(payload && payload.userId && users[payload.userId]){
        u = users[payload.userId];
        u.socketId = socket.id;
        sockets[socket.id] = u.id;
      } else {
        u = makeUser(payload && payload.name ? payload.name : undefined);
        u.socketId = socket.id;
        sockets[socket.id] = u.id;
      }
      cb && cb({ ok:true, user: { id: u.id, name: u.name, wins: u.wins, losses: u.losses, preferred: u.preferred } });
      io.emit('users:update', publicUsers());
    } catch(err){
      console.error(err);
      cb && cb({ ok:false, error: err.message });
    }
  });

  socket.on('profile:update', ({ userId, name, preferred }, cb) => {
    if(users[userId]){ if(name) users[userId].name = name; if(preferred) users[userId].preferred = preferred; io.emit('users:update', publicUsers()); cb && cb({ ok:true }); }
    else cb && cb({ ok:false, error:'user not found' });
  });

  socket.on('rooms:list', (payload, cb) => {
    cb && cb({ ok:true, rooms: Object.values(rooms).map(r=>summarizeRoom(r.id)) });
  });

  socket.on('room:create', ({ hostId, opening }, cb) => {
    if(!users[hostId]) return cb && cb({ ok:false, error:'host not found' });
    const roomId = nanoid(6);
    rooms[roomId] = { id: roomId, hostId, players: [hostId], opening: { [hostId]: opening || users[hostId].preferred || 'slave' }, state:'waiting', hands:{}, played:{}, discards:{} };
    socket.join(roomId);
    cb && cb({ ok:true, room: summarizeRoom(roomId) });
    io.emit('rooms:update', Object.values(rooms).map(r=>summarizeRoom(r.id)));
  });

  socket.on('room:join', ({ roomId, userId }, cb) => {
    const room = rooms[roomId];
    if(!room) return cb && cb({ ok:false, error:'room not found' });
    if(!users[userId]) return cb && cb({ ok:false, error:'user not found' });
    if(!room.players.includes(userId)) room.players.push(userId);
    room.opening[userId] = users[userId].preferred || 'slave';
    socket.join(roomId);
    io.to(roomId).emit('room:update', summarizeRoom(roomId));
    cb && cb({ ok:true, room: summarizeRoom(roomId) });
    if(room.players.length === 2){
      io.to(roomId).emit('room:ready', { roomId });
    }
  });

  socket.on('room:leave', ({ roomId, userId }, cb) => {
    const room = rooms[roomId];
    if(!room) return cb && cb({ ok:false, error:'room not found' });
    room.players = room.players.filter(p=>p!==userId);
    delete room.opening[userId];
    socket.leave(roomId);
    io.emit('rooms:update', Object.values(rooms).map(r=>summarizeRoom(r.id)));
    cb && cb({ ok:true });
    if(room.players.length === 0) delete rooms[roomId];
  });

  socket.on('match:start', ({ roomId }, cb) => {
    const room = rooms[roomId];
    if(!room) return cb && cb({ ok:false, error:'room not found' });
    if(room.players.length < 2) return cb && cb({ ok:false, error:'need 2 players' });
    // init hands
    room.hands = {};
    room.discards = {};
    room.played = {};
    room.state = 'playing';
    room.players.forEach(pid=>{
      const opening = room.opening[pid] || (users[pid] ? users[pid].preferred : 'slave');
      room.hands[pid] = shuffle(cloneDeckForRoom(opening));
      room.discards[pid] = [];
    });
    io.to(roomId).emit('match:started', { roomId, players: room.players, counts: room.players.map(pid=>({ pid, count: room.hands[pid].length })) });
    cb && cb({ ok:true });
  });

  // when client plays: { roomId, userId, cardId } where cardId is _id
  socket.on('match:play', ({ roomId, userId, cardId }, cb) => {
    const room = rooms[roomId];
    if(!room) return cb && cb({ ok:false, error:'room not found' });
    if(!room.hands[userId]) return cb && cb({ ok:false, error:'no hand' });
    const idx = room.hands[userId].findIndex(c=>c._id===cardId);
    if(idx === -1) return cb && cb({ ok:false, error:'card not found in hand' });
    const card = room.hands[userId].splice(idx,1)[0];
    room.played[userId] = card;
    io.to(roomId).emit('match:played', { roomId, userId, cardSummary: { name: card.name, tag: card.tag, lvl: card.lvl, _id: card._id } });
    // if both players played -> resolve
    if(Object.keys(room.played).length === room.players.length){
      resolveRoundServer(roomId);
    }
    cb && cb({ ok:true });
  });

  socket.on('disconnect', () => {
    const uid = sockets[socket.id];
    if(uid && users[uid]) users[uid].socketId = null;
    delete sockets[socket.id];
    io.emit('users:update', publicUsers());
    console.log('socket disconnected', socket.id);
  });
});

// clone deck helper
function cloneDeckForRoom(opening){
  const src = templates[opening] || templates['slave'];
  return shuffle(src.map(c=>({ ...JSON.parse(JSON.stringify(c)), _id: nanoid(8) })));
}

/* resolveRoundServer implements same rules as front-end. It takes room.played, room.hands, room.discards.
   It emits 'match:resolved' with events and updated hands/discards.
*/
function resolveRoundServer(roomId){
  const room = rooms[roomId];
  if(!room) return;
  const pids = room.players;
  if(pids.length !== 2) return;
  const [A, B] = pids;
  const aCard = room.played[A];
  const bCard = room.played[B];
  const events = [];
  function discard(pid, card){ if(card) room.discards[pid].push(card); }

  // both assassins
  if(aCard.tag === 'assassin' && bCard.tag === 'assassin'){
    if(room.hands[B] && room.hands[B].length>0){ const idx=Math.floor(Math.random()*room.hands[B].length); const k=room.hands[B].splice(idx,1)[0]; room.discards[B].push(k); events.push({type:'assassin:draw', by:A, killed:k}); }
    if(room.hands[A] && room.hands[A].length>0){ const idx=Math.floor(Math.random()*room.hands[A].length); const k=room.hands[A].splice(idx,1)[0]; room.discards[A].push(k); events.push({type:'assassin:draw', by:B, killed:k}); }
    discard(A,aCard); discard(B,bCard); events.push({type:'assassin:bothdie'});
  }
  // butcher anywhere -> both die
  else if(aCard.tag === 'butcher' || bCard.tag === 'butcher'){
    discard(A,aCard); discard(B,bCard); events.push({type:'butcher:bothdie'});
  }
  // assassin vs non-assassin
  else if(aCard.tag === 'assassin' && bCard.tag !== 'assassin'){
    if(bCard.tag === 'butcher'){
      discard(A,aCard); discard(B,bCard); events.push({type:'assassin:vs:butcher'});
    } else {
      // server-side decision: default kill
      // Could accept client choice in advanced flow; for now we simulate kill with prob 0.5
      const choice = Math.random() < 0.5 ? 'kill' : 'draw';
      if(choice === 'kill'){ discard(B,bCard); discard(A,aCard); events.push({type:'assassin:kill', by:A, target:bCard}); }
      else { if(room.hands[B] && room.hands[B].length>0){ const idx=Math.floor(Math.random()*room.hands[B].length); const k=room.hands[B].splice(idx,1)[0]; room.discards[B].push(k); events.push({type:'assassin:draw', by:A, killed:k}); } discard(A,aCard); }
    }
  }
  else if(bCard.tag === 'assassin' && aCard.tag !== 'assassin'){
    if(aCard.tag === 'butcher'){ discard(A,aCard); discard(B,bCard); events.push({type:'assassin:vs:butcher'}); }
    else {
      const choice = Math.random()<0.6 ? 'kill' : 'draw';
      if(choice === 'kill'){ discard(A,aCard); discard(B,bCard); events.push({type:'assassin:kill', by:B, target:aCard}); }
      else { if(room.hands[A] && room.hands[A].length>0){ const idx=Math.floor(Math.random()*room.hands[A].length); const k=room.hands[A].splice(idx,1)[0]; room.discards[A].push(k); events.push({type:'assassin:draw', by:B, killed:k}); } discard(B,bCard); }
    }
  }
  // ultguard vs assassin
  else if(aCard.tag === 'ultguard' && bCard.tag === 'assassin'){
    discard(B,bCard); room.hands[A].push(aCard); events.push({type:'ultguard:kills_assassin', by:A});
  }
  else if(bCard.tag === 'ultguard' && aCard.tag === 'assassin'){
    discard(A,aCard); room.hands[B].push(bCard); events.push({type:'ultguard:kills_assassin', by:B});
  }
  else {
    // slave beats king
    if(aCard.tag === 'slave' && bCard.tag === 'king'){
      room.hands[A].push(aCard); discard(B,bCard); events.push({type:'special', winner:A});
    } else if (bCard.tag === 'slave' && aCard.tag === 'king'){
      room.hands[B].push(bCard); discard(A,aCard); events.push({type:'special', winner:B});
    } else {
      if(aCard.lvl > bCard.lvl){ room.hands[A].push(aCard); discard(B,bCard); events.push({type:'normal', winner:A}); }
      else if(aCard.lvl < bCard.lvl){ room.hands[B].push(bCard); discard(A,aCard); events.push({type:'normal', winner:B}); }
      else { discard(A,aCard); discard(B,bCard); events.push({type:'tie'}); }
    }
  }

  // clear played
  room.played = {};

  // queen death handling => spawn king instantly and remove ultguard
  room.players.forEach(pid=>{
    const qIdx = room.discards[pid].findIndex(c=>c.tag==='queen');
    if(qIdx !== -1){
      // remove ultguard from hand/discard
      room.hands[pid] = room.hands[pid].filter(c=>c.tag!=='ultguard');
      // spawn king
      if(!room.hands[pid].some(c=>c.tag==='king')) room.hands[pid].push({ name:'国王', tag:'king', lvl:3, _id: nanoid(8) });
      events.push({ type:'queen:died', who:pid });
    }
  });

  // broadcast resolved
  io.to(roomId).emit('match:resolved', { room: summarizeRoom(roomId), events, counts: room.players.map(pid=>({ pid, count: room.hands[pid].length })) });

  // check victory: king in discards -> opponent wins
  room.players.forEach(pid=>{
    if(room.discards[pid].some(c=>c.tag==='king')){
      const winner = room.players.find(x=>x!==pid);
      room.state = 'finished';
      io.to(roomId).emit('match:finished', { winner, room: summarizeRoom(roomId) });
      // update records if users exist
      if(users[winner]) users[winner].wins++;
      if(users[pid]) users[pid].losses++;
      io.emit('users:update', publicUsers());
    }
  });
}

// ---------- REST endpoints (simple) ----------
app.get('/api/ping', (req, res) => res.json({ ok:true, ts: Date.now() }));
app.get('/api/users', (req, res) => res.json({ ok:true, users: publicUsers() }));
app.get('/api/rooms', (req, res) => res.json({ ok:true, rooms: Object.values(rooms).map(r=>summarizeRoom(r.id)) }));

const PORT = process.env.PORT || 3000;
server.listen(PORT, ()=> console.log('Server listening on', PORT));
