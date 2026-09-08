from worker.adapters.jsonld import extract_from_html
from worker.models import detect_site

HTML_JSONLD = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"LG OLED65C5","sku":"OLED65C5","model":"OLED65C5",
 "image":["https://img.example/a.jpg"],
 "offers":{"@type":"Offer","price":"2,890,000","priceCurrency":"KRW","availability":"https://schema.org/InStock",
           "seller":{"@type":"Organization","name":"LG전자"}}}
</script></head><body></body></html>
"""

HTML_OG = """
<meta property="og:title" content="Anker 737">
<meta property="product:price:amount" content="89.99">
<meta property="product:price:currency" content="USD">
"""


def test_jsonld_product():
    q = extract_from_html(HTML_JSONLD)
    assert q and q.price == 2_890_000 and q.currency == "KRW"
    assert q.title == "LG OLED65C5" and q.model_no == "OLED65C5" and q.seller == "LG전자"
    assert q.in_stock and q.image_url == "https://img.example/a.jpg"


def test_og_fallback():
    q = extract_from_html(HTML_OG)
    assert q and q.price == 89.99 and q.currency == "USD" and q.title == "Anker 737"


def test_nothing():
    assert extract_from_html("<html></html>") is None


def test_detect_site():
    assert detect_site("https://www.coupang.com/vp/products/123") == ("coupang", "KR", "KRW")
    assert detect_site("https://ko.aliexpress.com/item/100500.html") == ("aliexpress", "CN", "USD")
    assert detect_site("https://www.ebay.com/itm/123456789012") == ("ebay", "US", "USD")
    assert detect_site("https://shop.example.com/x") == ("generic", "US", "USD")
