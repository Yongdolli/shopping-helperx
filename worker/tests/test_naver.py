from worker.adapters.naver import extract_from_state
from worker.models import detect_site

HTML = """
<html><head><script>
window.__PRELOADED_STATE__ = {"product":{"A":{"id":123456,"name":"브랜드 무선 청소기 V12","salePrice":599000,
 "statusType":"SALE","stockQuantity":12,"channel":{"channelName":"브랜드공식스토어"},
 "representImage":{"url":"https://img.example/v12.jpg"},
 "benefitsView":{"discountedSalePrice":479000,"mobileDiscountedSalePrice":479000}}}};
</script></head><body></body></html>
"""

HTML_SOLDOUT = """
<script>window.__PRELOADED_STATE__ = {"x":{"name":"품절템","salePrice":10000,"statusType":"OUTOFSTOCK","stockQuantity":0}};</script>
"""


def test_extract_state_discounted():
    q = extract_from_state(HTML)
    assert q and q.price == 479000 and q.list_price == 599000 and q.currency == "KRW"
    assert q.title == "브랜드 무선 청소기 V12" and q.seller == "브랜드공식스토어" and q.in_stock
    assert q.external_id == "123456" and q.image_url == "https://img.example/v12.jpg"


def test_extract_state_soldout():
    q = extract_from_state(HTML_SOLDOUT)
    assert q and q.price == 10000 and q.list_price is None and not q.in_stock


def test_extract_state_missing():
    assert extract_from_state("<html>no state</html>") is None


def test_detect_naver():
    assert detect_site("https://smartstore.naver.com/somestore/products/123")[0] == "naver"
    assert detect_site("https://brand.naver.com/lg/products/9")[0] == "naver"
