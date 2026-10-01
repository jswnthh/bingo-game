const BINGO_FLASH_MS = 2800;
const WS_MAX_RECONNECT = 5;
const WS_BASE_MS = 1200;
const SHARE_TOAST_MS = 2000;

let bingoFlashTimer = null;
let shareToastTimer = null;
let announcedLineIndices = new Set();
let roomSocket = null;
let reconnectAttempts = 0;
let reconnectTimer = null;

function loadAnnouncedLines(grid) {
  announcedLineIndices = new Set();
  if (!grid || !grid.dataset.completedLines) {
    return;
  }
  try {
    const parsed = JSON.parse(grid.dataset.completedLines);
    if (Array.isArray(parsed)) {
      parsed.forEach((index) => announcedLineIndices.add(index));
    }
  } catch {
    announcedLineIndices = new Set();
  }
}

function maybeAnnounceBingo(newLineIndices) {
  if (!Array.isArray(newLineIndices) || !newLineIndices.length) {
    return;
  }
  let hasFreshLine = false;
  newLineIndices.forEach((index) => {
    if (!announcedLineIndices.has(index)) {
      announcedLineIndices.add(index);
      hasFreshLine = true;
    }
  });
  if (hasFreshLine) {
    showBingoAnnouncement();
  }
}

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) {
    return meta.content;
  }
  const input = document.querySelector("[name=csrfmiddlewaretoken]");
  return input ? input.value : "";
}

function setCellMarked(button, marked) {
  button.classList.toggle("on", marked);
  button.setAttribute("aria-pressed", marked ? "true" : "false");

  let blot = button.querySelector(".blot");
  if (marked && !blot) {
    blot = document.createElement("div");
    blot.className = "blot";
    blot.setAttribute("aria-hidden", "true");
    button.appendChild(blot);
  } else if (!marked && blot) {
    blot.remove();
  }
}

function applyLineHighlights(grid, highlightPositions) {
  const highlightSet = new Set(highlightPositions);
  grid.querySelectorAll("[data-position]").forEach((el) => {
    const pos = Number(el.dataset.position);
    el.classList.toggle("line", highlightSet.has(pos));
  });
}

function showBingoAnnouncement(customLabel) {
  const win = document.getElementById("win");
  if (!win) {
    return;
  }
  const label = win.querySelector("b");
  if (label) {
    label.textContent = customLabel || "BINGO!";
  }
  win.classList.add("show");
  if (bingoFlashTimer) {
    window.clearTimeout(bingoFlashTimer);
  }
  bingoFlashTimer = window.setTimeout(() => {
    win.classList.remove("show");
  }, BINGO_FLASH_MS);
}

function localPlayerNickname() {
  const nick = document.querySelector(".play-meta-bar__nick");
  return nick ? nick.textContent.trim() : "";
}

function showRemoteBingo(playerName) {
  if (playerName && playerName === localPlayerNickname()) {
    return;
  }
  const win = document.getElementById("win");
  if (win) {
    showBingoAnnouncement(playerName ? `${playerName} — BINGO!` : "BINGO!");
    return;
  }
  const heading = document.querySelector(".scoreboard-heading");
  if (heading && playerName) {
    const previous = heading.textContent;
    heading.textContent = `${playerName} got BINGO!`;
    window.setTimeout(() => {
      heading.textContent = previous;
    }, BINGO_FLASH_MS);
  }
}

function initPlayGrid() {
  const grid = document.getElementById("grid");
  if (!grid || !grid.dataset.roomCode) {
    return;
  }

  loadAnnouncedLines(grid);

  grid.addEventListener("click", async (event) => {
    const button = event.target.closest("button.play-cell");
    if (!button || button.disabled) {
      return;
    }

    const url = button.dataset.markUrl;
    if (!url) {
      return;
    }

    button.disabled = true;
    try {
      const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-CSRFToken": getCsrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
      });

      if (!response.ok) {
        return;
      }

      const data = await response.json();
      setCellMarked(button, data.marked);
      applyLineHighlights(grid, data.highlight || []);
      maybeAnnounceBingo(data.new_line_indices);
    } catch {
      /* network error — leave cell unchanged */
    } finally {
      button.disabled = false;
      button.blur();
    }
  });
}

function showShareToast() {
  const hint = document.getElementById("share-hint");
  if (!hint) {
    return;
  }
  hint.textContent = "LINK COPIED ✓";
  hint.hidden = false;
  if (shareToastTimer) {
    window.clearTimeout(shareToastTimer);
  }
  shareToastTimer = window.setTimeout(() => {
    hint.hidden = true;
  }, SHARE_TOAST_MS);
}

function initShareButton() {
  const button = document.getElementById("share-room");
  const hint = document.getElementById("share-hint");
  if (!button) {
    return;
  }

  button.addEventListener("click", async () => {
    const url = button.dataset.url;
    const title = button.dataset.title || "Prof Bingo";

    if (navigator.share) {
      try {
        await navigator.share({ title, url });
        return;
      } catch (err) {
        if (err.name === "AbortError") {
          return;
        }
      }
    }

    try {
      await navigator.clipboard.writeText(url);
      showShareToast();
    } catch {
      window.prompt("Copy this room link:", url);
    }
  });
}

function initWinOverlay() {
  const win = document.getElementById("win");
  if (!win) {
    return;
  }
  win.addEventListener("click", () => {
    win.classList.remove("show");
    if (bingoFlashTimer) {
      window.clearTimeout(bingoFlashTimer);
      bingoFlashTimer = null;
    }
  });

  if (win.classList.contains("show")) {
    showBingoAnnouncement();
  }
}

function getCurrentPlayerId() {
  const board = document.getElementById("scoreboard");
  if (!board || !board.dataset.currentPlayerId) {
    return null;
  }
  const id = Number(board.dataset.currentPlayerId);
  return Number.isFinite(id) && id > 0 ? id : null;
}

function playersWithYouFlag(players) {
  const myId = getCurrentPlayerId();
  if (!myId) {
    return players;
  }
  return players.map((player) => ({
    ...player,
    is_you: player.id === myId,
  }));
}

function formatPlayerStatus(me) {
  if (!me) {
    return "—";
  }
  const marks = `${me.marked} MARK${me.marked === 1 ? "" : "S"}`;
  if (me.bingo || me.lines > 0) {
    const lines =
      me.lines === 1 ? "1 LINE" : `${me.lines} LINES`;
    return `${marks} · ${lines}`;
  }
  return marks;
}

function updatePlayerStatusStrip(players) {
  const statsEl = document.getElementById("play-status-stats");
  if (!statsEl) {
    return;
  }
  const myId = getCurrentPlayerId();
  if (!myId) {
    return;
  }
  const me = (players || []).find((player) => player.id === myId);
  statsEl.textContent = formatPlayerStatus(me);
}

function renderScoreboard(tbody, players) {
  tbody.replaceChildren();
  const rows = playersWithYouFlag(players || []);
  const isPlayBoard = document
    .getElementById("scoreboard")
    ?.classList.contains("scoreboard--play");

  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "score-empty";
    cell.textContent = "No players yet.";
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  rows.forEach((player, index) => {
    const row = document.createElement("tr");
    if (player.is_you) {
      row.classList.add("score-you");
    }

    const rank = document.createElement("td");
    rank.className = "score-col-rank";
    rank.textContent = String(index + 1);

    const name = document.createElement("td");
    name.className = "score-name score-col-player";
    name.textContent = player.nickname;
    if (player.is_you && isPlayBoard) {
      const you = document.createElement("span");
      you.className = "score-you-label";
      you.textContent = " (YOU)";
      name.appendChild(you);
    } else if (player.is_you) {
      const tag = document.createElement("span");
      tag.className = "score-tag";
      tag.textContent = "you";
      name.appendChild(document.createTextNode(" "));
      name.appendChild(tag);
    }

    const marked = document.createElement("td");
    marked.className = "score-col-num";
    marked.textContent = String(player.marked);

    const lines = document.createElement("td");
    lines.className = "score-col-num";
    if (player.bingo && isPlayBoard) {
      const stamp = document.createElement("span");
      stamp.className = "score-bingo-stamp";
      stamp.textContent = "BINGO";
      lines.appendChild(stamp);
    } else {
      lines.textContent = String(player.lines);
      if (player.bingo && !isPlayBoard) {
        const bingo = document.createElement("span");
        bingo.className = "score-bingo-tag";
        bingo.textContent = "BINGO";
        name.appendChild(document.createTextNode(" "));
        name.appendChild(bingo);
      }
    }

    row.append(rank, name, marked, lines);
    tbody.appendChild(row);
  });
}

function updateScoreboardFromServer(players) {
  const tbody = document.getElementById("scoreboard-body");
  if (!tbody) {
    return;
  }
  renderScoreboard(tbody, players);
  updatePlayerStatusStrip(players);
}

function updatePlayerCount(count) {
  const countEl = document.getElementById("lobby-player-count");
  const pluralEl = document.getElementById("lobby-player-count-plural");
  if (!countEl || typeof count !== "number") {
    return;
  }
  countEl.textContent = String(count);
  if (pluralEl) {
    pluralEl.textContent = count === 1 ? "" : "s";
  }
}

function getRoomCode() {
  const board = document.getElementById("scoreboard");
  if (board?.dataset.roomCode) {
    return board.dataset.roomCode.trim().toUpperCase();
  }
  const grid = document.getElementById("grid");
  if (grid?.dataset.roomCode) {
    return grid.dataset.roomCode.trim().toUpperCase();
  }
  return null;
}

function handleRoomSocketMessage(event) {
  let data;
  try {
    data = JSON.parse(event.data);
  } catch {
    return;
  }

  switch (data.type) {
    case "score_update":
      updateScoreboardFromServer(data.players);
      break;
    case "player_joined":
      updatePlayerCount(data.player_count);
      break;
    case "bingo":
      showRemoteBingo(data.player);
      break;
    default:
      break;
  }
}

function scheduleReconnect(roomCode) {
  if (reconnectAttempts >= WS_MAX_RECONNECT) {
    return;
  }
  reconnectAttempts += 1;
  const delay = WS_BASE_MS * reconnectAttempts;
  reconnectTimer = window.setTimeout(() => {
    connectRoomSocket(roomCode);
  }, delay);
}

function connectRoomSocket(roomCode) {
  if (!roomCode) {
    return;
  }

  if (roomSocket) {
    roomSocket.close();
    roomSocket = null;
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${window.location.host}/ws/room/${encodeURIComponent(roomCode)}/`;

  roomSocket = new WebSocket(url);

  roomSocket.addEventListener("open", () => {
    reconnectAttempts = 0;
  });

  roomSocket.addEventListener("message", handleRoomSocketMessage);

  roomSocket.addEventListener("close", () => {
    roomSocket = null;
    scheduleReconnect(roomCode);
  });

  roomSocket.addEventListener("error", () => {
    roomSocket?.close();
  });
}

function initRoomWebSocket() {
  const roomCode = getRoomCode();
  if (!roomCode) {
    return;
  }
  connectRoomSocket(roomCode);

  window.addEventListener("beforeunload", () => {
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer);
    }
    if (roomSocket) {
      roomSocket.close();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initShareButton();
  initWinOverlay();
  initRoomWebSocket();
  initPlayGrid();
});
