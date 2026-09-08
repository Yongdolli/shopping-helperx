// 자동 생성 — 수정하지 말고 extension/build.mjs 를 실행하세요.
(function () {
  if (window.__shoppingHelperLoaded) return;
  window.__shoppingHelperLoaded = true;

  function capture(APP) {
    var d=document,P=null,L=null,T=d.title,C='';
function n(s){if(s==null)return null;var m=String(s).replace(/,/g,'').match(/\d+(\.\d+)?/);return m?parseFloat(m[0]):null}
function w(o,f){if(!o||typeof o!=='object')return;if(f(o))return true;for(var k in o){if(w(o[k],f))return true}}
function st(){if(window.__PRELOADED_STATE__)return window.__PRELOADED_STATE__;var ss=d.querySelectorAll('script');for(var i=0;i<ss.length;i++){var t=ss[i].textContent||'';var k=t.indexOf('__PRELOADED_STATE__');if(k<0)continue;var j=t.indexOf('{',k);var e=t.lastIndexOf('}');if(j<0||e<j)continue;try{return JSON.parse(t.slice(j,e+1))}catch(x){}}return null}
try{var ss=d.querySelectorAll('script[type="application/ld+json"]');for(var i=0;i<ss.length&&!P;i++){try{w(JSON.parse(ss[i].textContent),function(o){var t=o['@type'];if(t==='Product'||(Array.isArray(t)&&t.indexOf('Product')>-1)){var of=o.offers;if(Array.isArray(of))of=of[0];if(of&&typeof of==='object'){P=n(of.price||of.lowPrice);C=of.priceCurrency||C;T=o.name||T;return !!P}}})}catch(e){}}}catch(e){}
if(!P){var m=d.querySelector('meta[property="product:price:amount"],meta[property="og:price:amount"]');if(m)P=n(m.content);var c=d.querySelector('meta[property="product:price:currency"],meta[property="og:price:currency"]');if(c)C=c.content;var o=d.querySelector('meta[property="product:original_price:amount"]');if(o)L=n(o.content)}
var S=P?null:st();if(!P&&S){w(S,function(o){if(o.salePrice&&o.name){var b=o.benefitsView||{};var ds=n(b.discountedSalePrice||b.mobileDiscountedSalePrice||o.discountedSalePrice);var sp=n(o.salePrice);P=ds||sp;if(ds&&sp>ds)L=sp;T=o.name;C='KRW';return true}})}
if(!P){var sel=['.prod-sale-price .total-price strong','.total-price strong','#corePrice_feature_div .a-offscreen','.a-price .a-offscreen','[itemprop=price]','.price_real','.sale_price','.price'];for(var j=0;j<sel.length&&!P;j++){var e=d.querySelector(sel[j]);if(e)P=n(e.getAttribute('content')||e.textContent)}}
if(!C){var h=location.hostname;C=/\.kr$|naver|coupang|11st|gmarket|auction|danawa|ssg|lotteon|musinsa|kurly/.test(h)?'KRW':/taobao|tmall|jd\.com|1688/.test(h)?'CNY':'USD'}
if(!P){var v=prompt('가격을 찾지 못했습니다. 숫자만 입력:');P=n(v);if(!P)return}
var u=APP+'/capture?url='+encodeURIComponent(location.href.split('#')[0])+'&price='+P+'&currency='+C+'&title='+encodeURIComponent(T.slice(0,120))+(L?'&list_price='+L:'');
window.open(u,'_blank')
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === "SH_CAPTURE") capture(msg.appUrl);
  });

  // 상품 페이지로 보이면(가격 메타/JSON-LD Product 존재) 오른쪽 아래 플로팅 버튼
  function looksLikeProduct() {
    if (document.querySelector('meta[property="product:price:amount"],meta[property="og:price:amount"]')) return true;
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) if (/"@type"\s*:\s*"?Product/.test(s.textContent || "")) return true;
    for (const s of document.querySelectorAll('script')) if ((s.textContent || '').indexOf('__PRELOADED_STATE__') >= 0) return true;
    return /coupang\.com\/vp\/products|amazon\.[a-z.]+\/(dp|gp\/product)|smartstore\.naver\.com|11st\.co\.kr\/products|aliexpress\.[a-z]+\/item|ebay\.com\/itm|bestbuy\.com\/site|danawa\.com\/info/.test(location.href);
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
