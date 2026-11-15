// Закрите поле списку в стилі інтерфейсу (Chromium: customizable select). Вбудована кнопка поля не стилізується, тому в кожен
// <select> додаємо власну: <button><selectedcontent></selectedcontent></button> — тоді довгий вибраний пункт обрізається
// з «…» в одному рядку, а стрілка лишається на місці. Без підтримки base-select нічого не робимо.
const supported = typeof CSS !== "undefined" && CSS.supports?.("appearance", "base-select");

function enhance(select) {
  if (select.multiple || select.size > 1 || select.querySelector(":scope > button")) return;
  const button = document.createElement("button");
  button.type = "button";
  button.append(document.createElement("selectedcontent"));
  select.prepend(button);
}

if (supported) {
  const all = (root) => (root.nodeType === 1 ? [...(root.matches("select") ? [root] : []), ...root.querySelectorAll("select")] : []);
  for (const select of document.querySelectorAll("select")) enhance(select);
  // списки, які модулі створюють пізніше або наповнюють заново (innerHTML прибирає нашу кнопку)
  new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.target.nodeName === "SELECT") enhance(m.target);
      for (const node of m.addedNodes) for (const select of all(node)) enhance(select);
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
}
