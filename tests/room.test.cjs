const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');

function harness() {
  const timers = new Map();
  let nextTimer = 1;
  const status = { dataset: {}, textContent: '' };
  const board = { dataset: { roomCode: 'ABCDEF', scoresUrl: '/room/ABCDEF/scores/', currentPlayerId: '1' } };
  const sockets = [];
  class WebSocket {
    static OPEN = 1;
    constructor() { this.listeners = {}; this.readyState = 0; sockets.push(this); }
    addEventListener(type, fn) { this.listeners[type] = fn; }
    emit(type, data) { this.listeners[type]?.(data); }
    close() { this.readyState = 3; this.emit('close'); }
    send(data) { this.sent = data; }
  }
  const context = vm.createContext({
    WebSocket, URL, AbortController, console,
    sessionStorage: { getItem: () => null, setItem() {} },
    document: {
      getElementById: id => id === 'scoreboard' ? board : id === 'connection-status' ? status : null,
      addEventListener() {}, querySelector: () => null,
    },
    window: {
      location: { protocol: 'https:', host: 'example.test', href: 'https://example.test/' },
      setTimeout(fn, delay) { const id = nextTimer++; timers.set(id, { fn, delay }); return id; },
      clearTimeout(id) { timers.delete(id); }, addEventListener() {},
    },
    fetch: async () => ({ ok: true, json: async () => ({ players: [], events: [], event_cursor: 0 }) }),
  });
  vm.runInContext(fs.readFileSync('static/room.js', 'utf8'), context);
  const run = code => vm.runInContext(code, context);
  const fire = id => { const timer = timers.get(id); timers.delete(id); timer.fn(); };
  run('var announcements = []; showRemoteBingo = name => announcements.push(name);');
  return { run, timers, fire, sockets, status, context };
}

test('retries beyond five failures, with bounded backoff', () => {
  const h = harness();
  for (let i = 0; i < 12; i++) {
    h.run("scheduleReconnect('ABCDEF')");
    const id = h.run('reconnectTimer');
    assert.ok(h.timers.get(id).delay <= 30000);
    h.fire(id);
    h.sockets.at(-1).emit('close');
  }
  assert.equal(h.sockets.length, 12);
  assert.notEqual(h.run('reconnectTimer'), null);
});

test('stale socket callbacks cannot disconnect the replacement', () => {
  const h = harness();
  h.run("connectRoomSocket('ABCDEF')");
  const old = h.sockets[0];
  old.emit('error');
  h.fire(h.run('reconnectTimer'));
  old.emit('close');
  old.emit('error');
  assert.equal(h.run('roomSocket'), h.sockets[1]);
});

test('heartbeat timeout reconnects a silently broken connection', () => {
  const h = harness();
  h.run("connectRoomSocket('ABCDEF')");
  const socket = h.sockets[0];
  socket.readyState = 1;
  socket.emit('message', { data: '{"type":"pong"}' });
  assert.equal(h.status.dataset.state, 'live');
  h.fire(h.run('socketTimer'));
  assert.equal(socket.sent, '{"type":"ping"}');
  h.fire(h.run('socketTimer'));
  assert.equal(h.status.dataset.state, 'reconnecting');
  assert.equal(h.run('roomSocket'), null);
});

test('HTTP recovery announces missed bingo once, including same-named players', async () => {
  const h = harness();
  h.run('eventCursor = 3');
  h.context.fetch = async () => ({ ok: true, json: async () => ({
    players: [], events: [{ event_id: 4, player_id: 2, player: 'Remote' }], event_cursor: 4,
  }) });
  await h.run("refreshScores('ABCDEF')");
  h.run('receiveBingo({ event_id: 4, player_id: 2, player: "Remote" })');
  assert.equal(h.run('announcements.length'), 1);
  assert.equal(h.run('eventCursor'), 4);
  assert.equal(h.status.dataset.state, 'reconnecting');
});

test('live delivery does not advance recovery cursor past an earlier missing event', async () => {
  const h = harness();
  h.run('eventCursor = 3; receiveBingo({ event_id: 5, player_id: 2, player: "Later" })');
  assert.equal(h.run('eventCursor'), 3);
  h.context.fetch = async () => ({ ok: true, json: async () => ({
    players: [], events: [{ event_id: 4, player_id: 2, player: 'Earlier' }, { event_id: 5, player_id: 2, player: 'Later' }], event_cursor: 5,
  }) });
  await h.run("refreshScores('ABCDEF')");
  h.fire(h.run('remoteBingoTimer'));
  assert.equal(h.run('announcements.join(",")'), 'Later,Earlier');
});

test('own bingo is suppressed by player ID', () => {
  const h = harness();
  h.run('receiveBingo({ event_id: 1, player_id: 1, player: "Me" })');
  assert.equal(h.run('announcements.length'), 0);
});

test('failed fallback fetch retries and shows interrupted status', async () => {
  const h = harness();
  h.context.fetch = async () => { throw new Error('offline'); };
  await h.run("refreshScores('ABCDEF')");
  assert.equal(h.status.dataset.state, 'offline');
  assert.equal(h.timers.get(h.run('pollTimer')).delay, 5000);
});

test('in-flight fallback snapshot cannot overwrite a newer socket score', async () => {
  const h = harness();
  h.run('var rendered = []; updateScoreboardFromServer = players => rendered.push(players[0]?.marked)');
  let finish;
  h.context.fetch = () => new Promise(resolve => { finish = resolve; });
  const pending = h.run("refreshScores('ABCDEF')");
  h.run('handleRoomSocketMessage({ data: JSON.stringify({type: "score_update", players: [{marked: 2}]}) })');
  finish({ ok: true, json: async () => ({ players: [{ marked: 1 }], events: [], event_cursor: 0 }) });
  await pending;
  assert.equal(h.run('rendered.join(",")'), '2');
});
