const DICE_DETECTOR_WS = "ws://127.0.0.1:8767";

let socket = null;

Hooks.once("init", () => {
  console.log("Dice Detector | module loaded");
});

Hooks.once("ready", () => {
  connectToDiceDetector();
});

function connectToDiceDetector() {
  try {
    socket = new WebSocket(DICE_DETECTOR_WS);

    socket.addEventListener("open", () => {
      console.log("Dice Detector | connected to dice detector");
      ui.notifications.info("Dice Detector connected");
    });

    socket.addEventListener("message", (event) => {
      handleRollMessage(event.data);
    });

    socket.addEventListener("close", () => {
      console.log("Dice Detector | disconnected, retrying in 5s");
      setTimeout(connectToDiceDetector, 5000);
    });

    socket.addEventListener("error", () => {
      socket?.close();
    });
  } catch (error) {
    console.error("Dice Detector | connection failed", error);
    setTimeout(connectToDiceDetector, 5000);
  }
}

function handleRollMessage(raw) {
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return;
  }

  if (payload.type !== "roll" || !payload.message) {
    return;
  }

  ChatMessage.create({
    content: payload.message,
    speaker: ChatMessage.getSpeaker(),
    type: CONST.CHAT_MESSAGE_TYPES.OTHER,
  });
}
