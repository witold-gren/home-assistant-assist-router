// Every question to Home Assistant has a time limit: a Home Assistant that does not answer (restarting, a lost
// connection) ends in a clear message instead of a button that waits for ever (standard section 9a).
import { translate } from "./i18n.js";

export const WS_TIMEOUT_MS = 60000;

/** Home Assistant did not answer in time. */
export class WsTimeout extends Error {
  constructor(message, type) {
    super(message);
    this.name = "WsTimeout";
    this.code = "timeout";
    this.type = type;
  }
}

/** hass.callWS with a time limit (ms); the timer is cleared as soon as the answer comes. */
export function callWS(hass, message, ms = WS_TIMEOUT_MS) {
  let timer;
  const late = new Promise((_, reject) => {
    timer = setTimeout(() => {
      const text = translate(hass?.language, "ws_timeout", { seconds: Math.round(ms / 1000), type: message.type });
      reject(new WsTimeout(text, message.type));
    }, ms);
  });
  return Promise.race([hass.callWS(message), late]).finally(() => clearTimeout(timer));
}
