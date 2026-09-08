const input = document.getElementById("appUrl");
chrome.storage.sync.get({ appUrl: "" }, (v) => { input.value = v.appUrl; });
document.getElementById("save").onclick = () => {
  const appUrl = input.value.trim().replace(/\/+$/, "");
  chrome.storage.sync.set({ appUrl }, () => { document.getElementById("msg").textContent = "저장됨 ✓"; });
};
