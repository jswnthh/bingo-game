const WELCOME_MS = 500;
const WELCOME_KEY = "prof-bingo-welcome-seen";

function initWelcomeSplash() {
  const welcome = document.getElementById("welcome");
  if (!welcome) {
    return;
  }

  if (sessionStorage.getItem(WELCOME_KEY)) {
    welcome.remove();
    return;
  }

  setTimeout(() => {
    welcome.remove();
    sessionStorage.setItem(WELCOME_KEY, "1");
  }, WELCOME_MS);
}

function initRoomCodeInputs() {
  document.querySelectorAll(".code-row input").forEach((input) => {
    input.addEventListener("input", () => {
      const start = input.selectionStart;
      const end = input.selectionEnd;
      input.value = input.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
      if (start !== null && end !== null) {
        input.setSelectionRange(start, end);
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initWelcomeSplash();
  initRoomCodeInputs();
});
