from worker.adapters.danawa import extract_danawa
from worker.models import detect_site

HTML_A = '''<meta property="og:title" content="LG전자 OLED65C5 : 다나와 가격비교">
<div class="lowest_area"><p class="lwst_prc"><a><em class="prc_c">2,790,000</em>원</a></p>
<span class="mall_name"><img alt="지마켓"></span></div>'''
HTML_B = '<script>var lp = {"lowestPrice":"449000","lowestMallName":"쿠팡"};</script>'
HTML_C = '<html><body>가격 정보 없음</body></html>'


def test_html_block():
    q = extract_danawa(HTML_A)
    assert q and q.price == 2_790_000 and q.seller == "지마켓" and "OLED65C5" in (q.title or "")


def test_json_vars():
    q = extract_danawa(HTML_B)
    assert q and q.price == 449_000 and q.seller == "쿠팡"


def test_none():
    assert extract_danawa(HTML_C) is None


def test_site():
    assert detect_site("https://prod.danawa.com/info/?pcode=12345")[0] == "danawa"
