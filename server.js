/**
 * server.js
 * 王与奴 — 后端（MVP）
 * Node.js + Express + Socket.IO
 *
 * 注意：MVP 使用内存存储。生产请替换为持久化数据库与认证。
 */

require('dotenv').config(); // optional: npm i dotenv if you want
const express = require('express');
const http = require('http');
const { nanoid } = require('nanoid');
const cors = require('cors');
const app = express();
const server = http.createServer(app);
const io = require('socket.io')(server, {
  cors: { origin: process.env.CORS_ORIGIN || "*" }
});

app.use(cors());
app.use(express.json());
app.use(express.static('public')); // optional: serve frontend here

// --- In-memory stores (MVP) ---
const users = {};      // userId -> { id, name, socketId, wins, losses, friends:Set, openChoice }
const sockets = {};    // socketId -> userId
const rooms = {};      // roomId -> { id, players:[userId], state, opening: {userId:opening}, hands:{userId:[]}, played:{userId:card}, discards:{userId:[]}, hostId }

// ---------- Utility helpers ----------
const makeId = (len=8) => nanoid(len);
const clone = obj => JSON.parse(JSON.stringify(obj));
const shuffle = (arr) => {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
};

// ---------- Card templates ----------
const templates = {
  king: [
    { name: '市民', tag: 'citizen', lvl: 1 },
    { name: '市民', tag: 'citizen', lvl: 1 },
    { name: '刺客', tag: 'assassin', lvl: 2 },
    { name: '屠夫', tag: 'butcher', lvl: 2 },
    { name: '皇家守卫', tag: 'royalguard', lvl: 2 },
    { name: '国王', tag: 'king', lvl: 3 }
  ],
  queen: [
    { name: '市民', tag: 'citizen', lvl: 1 },
    { name: '市民', tag: 'citizen', lvl: 1 },
    { name: '刺客', tag: 'assassin', lvl: 2 },
    { name: '屠夫', tag: 'butcher', lvl: 2 },
    { name: '终极守卫', tag: 'ultguard', lvl: 3 },
    { name: '女王', tag: 'queen', lvl: 3 }
  ],
  slave: [
    { name: '奴隶', tag: 'slave', lvl: 0 },
    { name: '奴隶', tag: 'slave', lvl: 0 },
    { name: '市民', tag: 'citizen', lvl: 1 },
    { name: '市民', tag: 'citizen', lvl: 1 },
    { name: '守卫', tag: 'guard', lvl: 2 },
    { name: '刺客', tag: 'assassin', lvl: 2 },
    { name: '屠夫', tag: 'butcher', lvl: 2 }
  ]
};

function makeHand(opening) {
  if (!templates[opening]) opening = 'slave';
  return shuffle(clone(templates[opening]));
}

// ---------- Public helper to show users ----------
function publicUsers() {
  return Object.values(users).map(u => ({
    id: u.id,
    name: u.name,
    online: !!u.socketId,
    wins: u.wins,
    losses: u.losses
  }));
}

// ---------- Socket.IO handlers ----------
io.on('connection', socket => {
  console.log('socket connected:', socket.id);

  // Register or reconnect: { userId?, name? }
  socket.on('register', (payload, cb) => {
    try {
      let user;
      if (payload && payload.userId && users[payload.userId]) {
        // reconnect
        user = users[payload.userId];
        user.socketId = socket.id;
        sockets[socket.id] = user.id;
        console.log(`user reconnected: ${user.id} (${user.name})`);
      } else {
        // create new
        const id = makeId(8);
        user = { id, name: payload?.name || `玩家_${Math.floor(Math.random()*1000)}`, socketId: socket.id, wins: 0, losses: 0, friends: new Set(), openChoice: 'slave' };
        users[id] = user;
        sockets[socket.id] = id;
        console.log(`new user created: ${id} (${user.name})`);
      }
      // reply
      cb && cb({ ok: true, user: { id: user.id, name: user.name, wins: user.wins, losses: user.losses } });
      // broadcast user list
      io.emit('users:update', publicUsers());
    } catch (err) {
      console.error(err);
      cb && cb({ ok: false, error: err.message });
    }
  });

  // Update profile (name, opening preference)
  socket.on('profile:update', ({ userId, name, opening }, cb) => {
    if (!users[userId]) return cb && cb({ ok:false, error:'user not found' });
    if (name) users[userId].name = name;
    if (opening && ['king','queen','slave'].includes(opening)) users[userId].openChoice = opening;
    io.emit('users:update', publicUsers());
    cb && cb({ ok:true, user: { id: users[userId].id, name: users[userId].name, opening: users[userId].openChoice } });
  });

  // Friend add (mutual)
  socket.on('friend:add', ({ fromId, toId }, cb) => {
    if (!users[fromId] || !users[toId]) return cb && cb({ ok:false, error:'user missing' });
    users[fromId].friends.add(toId);
    users[toId].friends.add(fromId);
    [fromId, toId].forEach(uid => { if (users[uid].socketId) io.to(users[uid].socketId).emit('friends:update', Array.from(users[uid].friends)); });
    cb && cb({ ok:true });
  });

  // Create room
  socket.on('room:create', ({ hostId, mode='private' }, cb) => {
    if (!users[hostId]) return cb && cb({ ok:false, error:'host not found' });
    const roomId = makeId(6);
    rooms[roomId] = {
      id: roomId,
      players: [hostId],
      hostId,
      mode,
      state: 'waiting',
      opening: { [hostId]: users[hostId].openChoice || 'slave' },
      hands: {},
      played: {},
      discards: {}
    };
    socket.join(roomId);
    cb && cb({ ok:true, room: rooms[roomId] });
    io.emit('rooms:update', summarizeRooms());
  });

  // List rooms
  socket.on('rooms:list', (payload, cb) => {
    cb && cb({ ok:true, rooms: summarizeRooms() });
  });

  // Join room
  socket.on('room:join', ({ roomId, userId }, cb) => {
    const room = rooms[roomId];
    if (!room) return cb && cb({ ok:false, error:'room not found' });
    if (!users[userId]) return cb && cb({ ok:false, error:'user not found' });
    if (!room.players.includes(userId)) room.players.push(userId);
    room.opening[userId] = users[userId].openChoice || 'slave';
    io.to(roomId).emit('room:update', summarizeRoom(roomId));
    io.emit('rooms:update', summarizeRooms());
    // join socket room
    socket.join(roomId);
    cb && cb({ ok:true, room: summarizeRoom(roomId) });
    // if room full (2 players) => ready to start, notify
    if (room.players.length >= 2) {
      io.to(roomId).emit('room:ready', { roomId });
    }
  });

  // Leave room
  socket.on('room:leave', ({ roomId, userId }, cb) => {
    const room = rooms[roomId];
    if (!room) return cb && cb({ ok:false, error:'room not found' });
    room.players = room.players.filter(x => x !== userId);
    delete room.opening[userId];
    socket.leave(roomId);
    io.to(roomId).emit('room:update', summarizeRoom(roomId));
    io.emit('rooms:update', summarizeRooms());
    cb && cb({ ok:true });
    // if empty room -> remove
    if (room.players.length === 0) delete rooms[roomId];
  });

  // Start match (host triggers) - optionally pass openings per player
  socket.on('match:start', ({ roomId }, cb) => {
    const room = rooms[roomId];
    if (!room) return cb && cb({ ok:false, error:'room not found' });
    if (room.players.length < 2) return cb && cb({ ok:false, error:'need 2 players' });
    initMatch(roomId);
    cb && cb({ ok:true, room: summarizeRoom(roomId) });
  });

  // Play card inside match: { roomId, userId, cardIndex } where cardIndex is index in player's hand
  socket.on('match:play', ({ roomId, userId, cardIndex }, cb) => {
    const room = rooms[roomId];
    if (!room) return cb && cb({ ok:false, error:'room not found' });
    if (!room.hands[userId] || room.hands[userId].length <= cardIndex) return cb && cb({ ok:false, error:'invalid cardIndex' });
    const card = room.hands[userId][cardIndex];
    // remove from hand and mark as played
    room.hands[userId].splice(cardIndex, 1);
    room.played[userId] = card;
    io.to(roomId).emit('match:played', { userId, card });
    // if all players played -> resolve
    if (Object.keys(room.played).length === room.players.length) {
      resolveRound(roomId);
    }
    cb && cb({ ok:true });
  });

  // Request current room state
  socket.on('room:state', ({ roomId }, cb) => {
    cb && cb({ ok: !!rooms[roomId], room: summarizeRoom(roomId) });
  });

  // Disconnect handling
  socket.on('disconnect', () => {
    const uid = sockets[socket.id];
    if (uid && users[uid]) {
      users[uid].socketId = null;
      // optionally mark user offline
      console.log('user disconnected:', uid);
    }
    delete sockets[socket.id];
    io.emit('users:update', publicUsers());
  });
});

// ---------- Helpers: rooms summary ----------
function summarizeRoom(roomId) {
  const r = rooms[roomId];
  if (!r) return null;
  return {
    id: r.id,
    players: r.players.map(pid => ({ id: pid, name: users[pid]?.name || pid })),
    state: r.state,
    hostId: r.hostId,
    counts: r.players.reduce((o, pid) => { o[pid] = (r.hands[pid] ? r.hands[pid].length : 0); return o; }, {})
  };
}
function summarizeRooms() {
  return Object.values(rooms).map(r => summarizeRoom(r.id));
}

// ---------- Match lifecycle ----------
function initMatch(roomId) {
  const room = rooms[roomId];
  if (!room) return;
  room.state = 'playing';
  room.played = {};
  room.discards = {};
  room.hands = {};
  // build hand for each player based on their selected opening
  room.players.forEach(pid => {
    const opening = room.opening[pid] || users[pid]?.openChoice || 'slave';
    room.hands[pid] = makeHand(opening);
    room.discards[pid] = [];
  });
  io.to(roomId).emit('match:started', { roomId, players: room.players, counts: room.players.map(p => ({ pid: p, count: room.hands[p].length })) });
}

// resolveRound implements the game rules described in handbook (MVP simplified)
function resolveRound(roomId) {
  const room = rooms[roomId];
  if (!room) return;
  const pids = room.players;
  if (pids.length < 2) return;
  const [A, B] = pids;
  const aCard = room.played[A];
  const bCard = room.played[B];

  const events = [];
  function discard(pid, card){ if (card) room.discards[pid].push(card); }
  // Both assassins
  if (aCard.tag === 'assassin' && bCard.tag === 'assassin') {
    // each randomly remove one from opponent hand if exists
    if (room.hands[B] && room.hands[B].length > 0) { const idx = Math.floor(Math.random() * room.hands[B].length); const killed = room.hands[B].splice(idx,1)[0]; room.discards[B].push(killed); events.push({type:'assassin:draw', who:A, killed}) }
    if (room.hands[A] && room.hands[A].length > 0) { const idx = Math.floor(Math.random() * room.hands[A].length); const killed = room.hands[A].splice(idx,1)[0]; room.discards[A].push(killed); events.push({type:'assassin:draw', who:B, killed}) }
    // both assassins die
    discard(A, aCard); discard(B, bCard); events.push({type:'assassin:bothdie'});
  }
  // butcher anywhere -> both die
  else if (aCard.tag === 'butcher' || bCard.tag === 'butcher') {
    discard(A,aCard); discard(B,bCard); events.push({type:'butcher:bothdie'});
  }
  // assassin vs non
  else if (aCard.tag === 'assassin' && bCard.tag !== 'assassin') {
    if (bCard.tag === 'butcher') {
      discard(A,aCard); discard(B,bCard); events.push({type:'assassin:vs:butcher'});
    } else {
      // server-side random decision for AI / simulation; client could send choice in practice
      const choice = Math.random() < 0.5 ? 'kill' : 'draw';
      if (choice === 'kill') { discard(B,bCard); discard(A,aCard); events.push({type:'assassin:kill', who:A, target:bCard}); }
      else { if (room.hands[B] && room.hands[B].length>0){ const idx=Math.floor(Math.random()*room.hands[B].length); const k=room.hands[B].splice(idx,1)[0]; room.discards[B].push(k); events.push({type:'assassin:draw', who:A, killed:k}); } discard(A,aCard); }
    }
  }
  else if (bCard.tag === 'assassin' && aCard.tag !== 'assassin') {
    if (aCard.tag === 'butcher') {
      discard(A,aCard); discard(B,bCard); events.push({type:'assassin:vs:butcher'});
    } else {
      const choice = Math.random() < 0.5 ? 'kill' : 'draw';
      if (choice === 'kill') { discard(A,aCard); discard(B,bCard); events.push({type:'assassin:kill', who:B, target:aCard}); }
      else { if (room.hands[A] && room.hands[A].length>0){ const idx=Math.floor(Math.random()*room.hands[A].length); const k=room.hands[A].splice(idx,1)[0]; room.discards[A].push(k); events.push({type:'assassin:draw', who:B, killed:k}); } discard(B,bCard); }
    }
  }
  // ultguard kills assassin
  else if (aCard.tag === 'ultguard' && bCard.tag === 'assassin') {
    discard(B,bCard); // assassin dead
    // ultguard returns to hand (winner returns)
    room.hands[A].push(aCard);
    events.push({type:'ultguard:kills_assassin', who:A});
  }
  else if (bCard.tag === 'ultguard' && aCard.tag === 'assassin') {
    discard(A,aCard);
    room.hands[B].push(bCard);
    events.push({type:'ultguard:kills_assassin', who:B});
  }
  else {
    // slave beats king
    if (aCard.tag === 'slave' && bCard.tag === 'king') {
      room.hands[A].push(aCard); discard(B,bCard); events.push({type:'special', winner:A});
    } else if (bCard.tag === 'slave' && aCard.tag === 'king') {
      room.hands[B].push(bCard); discard(A,aCard); events.push({type:'special', winner:B});
    } else {
      // normal level compare
      if (aCard.lvl > bCard.lvl) { room.hands[A].push(aCard); discard(B,bCard); events.push({type:'normal', winner:A}); }
      else if (aCard.lvl < bCard.lvl) { room.hands[B].push(bCard); discard(A,aCard); events.push({type:'normal', winner:B}); }
      else { discard(A,aCard); discard(B,bCard); events.push({type:'tie'}); }
    }
  }

  // clear played
  room.played = {};

  // queen death trigger -> spawn king immediately and remove ultguard
  room.players.forEach(pid => {
    const diedQueenIndex = room.discards[pid].findIndex(c => c.tag === 'queen');
    if (diedQueenIndex !== -1) {
      // remove ultguard from hand/discards for that pid
      room.hands[pid] = room.hands[pid].filter(c => c.tag !== 'ultguard');
      room.discards[pid] = room.discards[pid].filter(c => !(c.tag === 'ultguard' && c._marker !== 'preserve'));
      // spawn king in hand if not present
      if (!room.hands[pid].some(c => c.tag === 'king')) room.hands[pid].push({ name: '国王', tag: 'king', lvl: 3 });
      events.push({ type: 'queen:died', who: pid });
    }
  });

  // emit resolved event + room updated
  io.to(roomId).emit('match:resolved', { room: summarizeRoom(roomId), events });

  // check victory: king in discard -> opponent wins round/match
  room.players.forEach(pid => {
    if (room.discards[pid].some(c => c.tag === 'king')) {
      const winner = room.players.find(x => x !== pid);
      room.state = 'finished';
      io.to(roomId).emit('match:finished', { room: summarizeRoom(roomId), winner });
    }
  });
}

// ---------- Utility: summary and cleanup ----------
function summarizeRoom(roomId) {
  const r = rooms[roomId];
  if (!r) return null;
  return {
    id: r.id,
    players: r.players.map(pid => ({ id: pid, name: users[pid]?.name || pid })),
    state: r.state,
    hostId: r.hostId,
    counts: r.players.reduce((o, pid) => { o[pid] = (r.hands[pid] ? r.hands[pid].length : 0); return o; }, {})
  };
}

// ---------- Simple express endpoints ----------
app.get('/api/ping', (req, res) => res.json({ ok: true, ts: Date.now() }));
app.get('/api/users', (req, res) => res.json({ ok:true, users: publicUsers() }));
app.get('/api/rooms', (req, res) => res.json({ ok:true, rooms: summarizeRooms() }));

// ---------- Start server ----------
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => console.log(`Server listening on port ${PORT}`));
