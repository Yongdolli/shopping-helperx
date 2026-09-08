// 툴바 버튼 클릭 → 현재 탭에서 가격 추출 실행
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;
  const { appUrl } = await chrome.storage.sync.get({ appUrl: "" });
  if (!appUrl) { chrome.runtime.openOptionsPage(); return; }
  chrome.tabs.sendMessage(tab.id, { type: "SH_CAPTURE", appUrl }).catch(async () => {
    // content script 가 아직 없는 탭(설치 직후) → 주입 후 재시도
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    chrome.tabs.sendMessage(tab.id, { type: "SH_CAPTURE", appUrl });
  });
});
