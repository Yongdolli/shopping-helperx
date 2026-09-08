/**
 * 북마클릿 "가격 기록": 지금 보고 있는 상품 페이지에서 가격을 읽어 앱의 /capture 로 넘긴다.
 * 서버 봇이 아니라 사용자 브라우저가 읽으므로 네이버·쿠팡·아마존 같은 봇 차단 사이트도 기록할 수 있다.
 * 추출 순서: JSON-LD Product → OpenGraph/product meta → 네이버 __PRELOADED_STATE__(window 또는 script 텍스트 — 확장의 isolated world 대응) → 사이트별 셀렉터 → 직접 입력.
 */
const SRC = `(function(){var d=document,P=null,L=null,T=d.title,C='';
function n(s){if(s==null)return null;var m=String(s).replace(/,/g,'').match(/\\d+(\\.\\d+)?/);return m?parseFloat(m[0]):null}
function w(o,f){if(!o||typeof o!=='object')return;if(f(o))return true;for(var k in o){if(w(o[k],f))return true}}
function st(){if(window.__PRELOADED_STATE__)return window.__PRELOADED_STATE__;var ss=d.querySelectorAll('script');for(var i=0;i<ss.length;i++){var t=ss[i].textContent||'';var k=t.indexOf('__PRELOADED_STATE__');if(k<0)continue;var j=t.indexOf('{',k);var e=t.lastIndexOf('}');if(j<0||e<j)continue;try{return JSON.parse(t.slice(j,e+1))}catch(x){}}return null}
try{var ss=d.querySelectorAll('script[type="application/ld+json"]');for(var i=0;i<ss.length&&!P;i++){try{w(JSON.parse(ss[i].textContent),function(o){var t=o['@type'];if(t==='Product'||(Array.isArray(t)&&t.indexOf('Product')>-1)){var of=o.offers;if(Array.isArray(of))of=of[0];if(of&&typeof of==='object'){P=n(of.price||of.lowPrice);C=of.priceCurrency||C;T=o.name||T;return !!P}}})}catch(e){}}}catch(e){}
if(!P){var m=d.querySelector('meta[property="product:price:amount"],meta[property="og:price:amount"]');if(m)P=n(m.content);var c=d.querySelector('meta[property="product:price:currency"],meta[property="og:price:currency"]');if(c)C=c.content;var o=d.querySelector('meta[property="product:original_price:amount"]');if(o)L=n(o.content)}
var S=P?null:st();if(!P&&S){w(S,function(o){if(o.salePrice&&o.name){var b=o.benefitsView||{};var ds=n(b.discountedSalePrice||b.mobileDiscountedSalePrice||o.discountedSalePrice);var sp=n(o.salePrice);P=ds||sp;if(ds&&sp>ds)L=sp;T=o.name;C='KRW';return true}})}
if(!P){var sel=['.prod-sale-price .total-price strong','.total-price strong','#corePrice_feature_div .a-offscreen','.a-price .a-offscreen','[itemprop=price]','.price_real','.sale_price','.price'];for(var j=0;j<sel.length&&!P;j++){var e=d.querySelector(sel[j]);if(e)P=n(e.getAttribute('content')||e.textContent)}}
if(!C){var h=location.hostname;C=/\\.kr$|naver|coupang|11st|gmarket|auction|danawa|ssg|lotteon|musinsa|kurly/.test(h)?'KRW':/taobao|tmall|jd\\.com|1688/.test(h)?'CNY':'USD'}
if(!P){var v=prompt('가격을 찾지 못했습니다. 숫자만 입력:');P=n(v);if(!P)return}
var u=__APP__+'/capture?url='+encodeURIComponent(location.href.split('#')[0])+'&price='+P+'&currency='+C+'&title='+encodeURIComponent(T.slice(0,120))+(L?'&list_price='+L:'');
window.open(u,'_blank')})();`;

export function bookmarkletHref(appOrigin: string): string {
  return "javascript:" + encodeURIComponent(SRC.replace("__APP__", JSON.stringify(appOrigin)));
}
