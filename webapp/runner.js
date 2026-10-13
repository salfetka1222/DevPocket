(() => {
const codeEl = document.getElementById("code");
const languageEl = document.getElementById("language");
const actions = document.querySelector(".actions");

if (!codeEl || !languageEl || !actions) return;

const style = document.createElement("style");
style.textContent = ".runner-panel { margin-top: 14px; padding: 12px; border: 1px solid var(--border); border-radius: 12px; background: #0c0f16; } .runner-buttons { display: grid; grid-template-columns: 1fr auto; gap: 8px; } .runner-output { min-height: 65px; max-height: 240px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; margin: 10px 0 0; padding: 12px; border: 1px solid var(--border); border-radius: 9px; background: #080a0f; color: var(--green); font: 12px/1.6 monospace; }";
document.head.appendChild(style);

const panel = document.createElement("section");
panel.className = "runner-panel";
panel.innerHTML = "<h2>▶ Запуск Python</h2> <div class="runner-buttons"> <button id="runner-start">▶ Запустить</button> <button id="runner-stop" class="secondary" disabled>■ Стоп</button> </div> <pre id="runner-output" class="runner-output">Результат появится здесь.</pre> <p class="notice" style="margin-top:8px"> Код выполняется в браузере, не на сервере DevPocket. Первый запуск может занять время на загрузку Python. Не запускай незнакомый код. </p>";
actions.insertAdjacentElement("afterend", panel);

const startBtn = document.getElementById("runner-start");
const stopBtn = document.getElementById("runner-stop");
const output = document.getElementById("runner-output");

let worker = null;
let workerUrl = null;
let timer = null;
let outputText = "";
let running = false;

const workerSource = `
let pyodide = null;
let outputLength = 0;

function sendOutput(text, isError) {
  const remaining = 12000 - outputLength;
  if (remaining <= 0) return;

  const part = String(text).slice(0, remaining);
  outputLength += part.length;

  self.postMessage({
    type: "output",
    text: part,
    isError: !!isError
  });
}

self.onmessage = async function(event) {
  if (!event.data || event.data.type !== "run") return;

  outputLength = 0;

  try {
    if (!pyodide) {
      self.postMessage({ type: "loading" });

      importScripts(
        "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js"
      );

      pyodide = await loadPyodide({
        indexURL:
          "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/"
      });
    }

    pyodide.setStdout({
      batched: text => sendOutput(text + "\\n", false)
    });

    pyodide.setStderr({
      batched: text => sendOutput(text + "\\n", true)
    });

    self.postMessage({ type: "ready" });

    await pyodide.runPythonAsync(event.data.code);

    self.postMessage({
      type: "done",
      hasOutput: outputLength > 0
    });
  } catch (error) {
    self.postMessage({
      type: "failure",
      message: String(error)
    });
  }
};

`;

function clearTimer() {
if (timer !== null) {
clearTimeout(timer);
timer = null;
}
}

function updateButtons() {
startBtn.disabled = running || languageEl.value !== "python";
stopBtn.disabled = !running;
}

function terminate(message) {
clearTimer();

if (worker) {
  worker.terminate();
  worker = null;
}

if (workerUrl) {
  URL.revokeObjectURL(workerUrl);
  workerUrl = null;
}

running = false;
updateButtons();

if (message) output.textContent = message;

}

function appendOutput(text) {
if (outputText.length >= 12000) return;

const remaining = 12000 - outputText.length;
outputText += text.slice(0, remaining);

if (outputText.length >= 12000) {
  outputText += "\\n…вывод ограничен 12 000 символами…";
}

output.textContent = outputText;

}

function createWorker() {
workerUrl = URL.createObjectURL(
new Blob([workerSource], { type: "text/javascript" })
);

worker = new Worker(workerUrl);

worker.onmessage = event => {
  const data = event.data || {};

  if (data.type === "loading") {
    output.textContent = "Загружаем Python-среду…";
  }

  if (data.type === "ready") {
    clearTimer();

    timer = setTimeout(() => {
      terminate(
        "Лимит выполнения — 5 секунд. Запуск остановлен."
      );
    }, 5000);

    output.textContent = "";
  }

  if (data.type === "output") {
    appendOutput(
      (data.isError ? "[stderr] " : "") + data.text
    );
  }

  if (data.type === "done") {
    clearTimer();
    running = false;
    updateButtons();

    if (!outputText.trim()) {
      output.textContent = "Программа завершилась без вывода.";
    }
  }

  if (data.type === "failure") {
    clearTimer();
    appendOutput("\\nОшибка:\\n" + data.message);
    running = false;
    updateButtons();
  }
};

worker.onerror = event => {
  terminate(
    "Не удалось запустить Python: " +
    (event.message || "ошибка загрузки")
  );
};

}

startBtn.addEventListener("click", () => {
if (running) return;

if (languageEl.value !== "python") {
  output.textContent = "Выбери язык Python.";
  return;
}

const code = codeEl.value;

if (!code.trim()) {
  output.textContent = "Сначала напиши Python-код.";
  return;
}

if (code.length > 50000) {
  output.textContent = "Максимальный размер кода — 50 000 символов.";
  return;
}

outputText = "";
output.textContent = "Подготовка запуска…";
running = true;
updateButtons();

try {
  if (!worker) createWorker();

  timer = setTimeout(() => {
    terminate(
      "Python загружается слишком долго. Проверь соединение."
    );
  }, 45000);

  worker.postMessage({ type: "run", code });
} catch (error) {
  terminate("Ошибка запуска: " + error.message);
}

});

stopBtn.addEventListener("click", () => {
terminate("Выполнение остановлено.");
});

languageEl.addEventListener("change", updateButtons);
updateButtons();
})();