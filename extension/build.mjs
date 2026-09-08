// 북마클릿과 같은 추출 로직(web/src/lib/bookmarklet.ts 의 SRC)을 content.js 로 생성.
// 실행: node extension/build.mjs   (web 소스가 바뀌면 다시 실행)
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const ts = readFileSync(join(here, "../web/src/lib/bookmarklet.ts"), "utf8");
const m = ts.match(/const SRC = `([\s\S]*?)`;/);
if (!m) throw new Error("bookmarklet.ts 에서 SRC 를 찾지 못함");
// 템플릿 리터럴 안의 이스케이프(\\d 등)를 실제 문자열로
const src = m[1].replace(/\\\\/g, "\\");
// 북마클릿은 즉시 실행(IIFE) — 확장에서는 함수로 감싸 필요할 때 호출
const fnBody = src.replace(/^\(function\(\)\{/, "").replace(/\}\)\(\);?\s*$/, "").replace(/__APP__/g, "APP");

const content = `// 자동 생성 — 수정하지 말고 extension/build.mjs 를 실행하세요.
(function () {
  if (window.__shoppingHelperLoaded) return;
  window.__shoppingHelperLoaded = true;

  function capture(APP) {
    ${fnBody}
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === "SH_CAPTURE") capture(msg.appUrl);
  });

  // 상품 페이지로 보이면(가격 메타/JSON-LD Product 존재) 오른쪽 아래 플로팅 버튼
  function looksLikeProduct() {
    if (document.querySelector('meta[property="product:price:amount"],meta[property="og:price:amount"]')) return true;
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) if (/"@type"\\s*:\\s*"?Product/.test(s.textContent || "")) return true;
    for (const s of document.querySelectorAll('script')) if ((s.textContent || '').indexOf('__PRELOADED_STATE__') >= 0) return true;
    return /coupang\\.com\\/vp\\/products|amazon\\.[a-z.]+\\/(dp|gp\\/product)|smartstore\\.naver\\.com|11st\\.co\\.kr\\/products|aliexpress\\.[a-z]+\\/item|ebay\\.com\\/itm|bestbuy\\.com\\/site|danawa\\.com\\/info/.test(location.href);
  }

  function mountButton() {
    if (document.getElementById("sh-capture-btn") || !looksLikeProduct()) return;
    const b = document.createElement("button");
    b.id = "sh-capture-btn";
    b.textContent = "📌 가격 기록";
    Object.assign(b.style, { position: "fixed", right: "16px", bottom: "16px", zIndex: 2147483647, padding: "10px 14px", borderRadius: "999px", border: "0",
      background: "#0284c7", color: "#fff", fontSize: "13px", fontWeight: "600", boxShadow: "0 4px 14px rgba(0,0,0,.25)", cursor: "pointer", fontFamily: "system-ui, sans-serif" });
    b.onclick = () => chrome.storage.sync.get({ appUrl: "" }, (v) => {
      if (!v.appUrl) { alert("Shopping Helper 확장 설정에서 앱 주소를 먼저 입력하세요."); return; }
      capture(v.appUrl);
    });
    document.body.appendChild(b);
  }
  if (document.readyState === "complete") mountButton(); else window.addEventListener("load", mountButton);
  setTimeout(mountButton, 2500); // SPA 로딩 대기
})();
`;
writeFileSync(join(here, "content.js"), content);
console.log("extension/content.js 생성 완료");
