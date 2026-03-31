"""
패션 리서치 자동 크롤러 v3
- __NEXT_DATA__ JSON 우선 파싱 (29cm, W컨셉 모두 Next.js SPA)
- og: 메타 태그 fallback
- 소재·혼용률·원산지·시즌 정규식 추출
- 네이버 블로그 API + 웹 fallback
- 인스타그램 3단계 시도
"""

import requests, re, time, random, json
from bs4 import BeautifulSoup
from urllib.parse import quote

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def _ua(): return random.choice(UA_POOL)

def make_session(referer=''):
    s = requests.Session()
    s.headers.update({
        'User-Agent': _ua(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    if referer:
        s.headers.update({'Referer': referer})
    return s

def human_delay(a=1.0, b=2.5): time.sleep(random.uniform(a, b))

def _safe_int(v):
    try: return int(str(v).replace(',','').replace(' ','').strip())
    except: return 0

# ── 텍스트에서 원단 정보 추출 ──────────────────────────────────────
def _extract_fabric(text: str) -> dict:
    fab = {'material':'', 'composition':'', 'weight':'', 'origin':''}

    # 혼용률: "폴리에스터 60%, 면 40%" / "cotton 80% polyester 20%"
    comp_patterns = [
        r'혼용률\s*[:\-]?\s*([가-힣a-zA-Z\s]+\d+%(?:\s*[,·/]\s*[가-힣a-zA-Z\s]+\d+%)*)',
        r'소재\s*[:\-]?\s*([가-힣a-zA-Z\s]+\d+%(?:\s*[,·/]\s*[가-힣a-zA-Z\s]+\d+%)*)',
        r'((?:면|폴리에스터|나일론|레이온|린넨|울|캐시미어|아크릴|모달|텐셀|cotton|polyester|nylon|rayon|linen|wool)\s*\d+%(?:\s*[,·/]\s*\S+\s*\d+%)*)',
    ]
    for pat in comp_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fab['composition'] = m.group(1).strip()[:100]
            break

    # 소재명 (단순 명칭)
    mat_patterns = [
        r'소재명\s*[:\-]?\s*([가-힣a-zA-Z]+)',
        r'원단\s*[:\-]?\s*([가-힣a-zA-Z]+)',
        r'(데님|린넨|면|코튼|캐시미어|울|나일론|폴리에스터|레이온|모달|텐셀|시폰|새틴|벨벳|트위드|플리스)',
    ]
    for pat in mat_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fab['material'] = m.group(1).strip()
            break

    # 원산지
    m = re.search(r'원산지\s*[:\-]?\s*([가-힣a-zA-Z\s]+?)(?:\n|,|\.|·)', text)
    if m: fab['origin'] = m.group(1).strip()

    # 중량/수
    m = re.search(r'(\d+\s*(?:oz|g/m²|수))', text, re.IGNORECASE)
    if m: fab['weight'] = m.group(1).strip()

    return fab

def _extract_season(text: str) -> str:
    m = re.search(r'\b((?:SS|FW|AW|RE|PF|PRE)\s*(?:20)?\d{2})\b', text, re.IGNORECASE)
    if m: return m.group(1).upper().replace(' ','')
    return ''

# ══════════════════════════════════════════════════════════════════
#  29cm / W컨셉 → Playwright 크롤러로 위임 (정확도·JS 렌더링 보장)
#  Playwright 미설치 시 requests 방식으로 자동 fallback
# ══════════════════════════════════════════════════════════════════

def crawl_29cm_product(url: str) -> dict:
    try:
        from crawler.playwright_crawl import crawl_29cm_product as _pw
        return _pw(url)
    except Exception:
        pass
    # ── Playwright 없을 때 requests fallback ──
    return _crawl_29cm_requests(url)

def crawl_wconcept_product(url: str) -> dict:
    try:
        from crawler.playwright_crawl import crawl_wconcept_product as _pw
        return _pw(url)
    except Exception:
        pass
    return _crawl_wconcept_requests(url)

def _crawl_29cm_requests(url: str) -> dict:
    result = {
        'success': False, 'name':'', 'price':0, 'image_url':'', 'brand':'',
        'fabric':{'material':'','composition':'','weight':'','origin':''},
        'season':'', 'error':''
    }
    sess = make_session()
    try:
        # 메인 방문으로 쿠키 획득
        try: sess.get('https://www.29cm.co.kr/', timeout=8)
        except: pass
        human_delay(0.6, 1.5)
        sess.headers.update({'Referer': 'https://www.29cm.co.kr/', 'User-Agent': _ua()})

        resp = sess.get(url, timeout=15)
        if resp.status_code != 200:
            result['error'] = f'HTTP {resp.status_code}'
            return result

        soup = BeautifulSoup(resp.text, 'html.parser')
        page_text = soup.get_text(' ', strip=True)

        # ── 1순위: __NEXT_DATA__ JSON 파싱 ──
        nd_script = soup.find('script', id='__NEXT_DATA__')
        if nd_script:
            try:
                nd = json.loads(nd_script.string or '{}')
                pp = nd.get('props',{}).get('pageProps',{})

                # 제품 데이터 위치 탐색 (사이트 구조에 따라 다름)
                item = (pp.get('product') or pp.get('item') or
                        pp.get('productDetail') or pp.get('data') or {})
                if not item and 'dehydratedState' in pp:
                    # React Query 캐시에서 추출
                    queries = pp['dehydratedState'].get('queries', [])
                    for q in queries:
                        qdata = q.get('state',{}).get('data',{})
                        if isinstance(qdata, dict) and (qdata.get('itemName') or qdata.get('productName')):
                            item = qdata
                            break

                if item:
                    result['name'] = (item.get('itemName') or item.get('productName') or
                                      item.get('name') or result['name'])
                    result['brand'] = (item.get('brandName') or item.get('brand') or
                                       item.get('brandNameEn') or result['brand'])
                    price_val = (item.get('consumerPrice') or item.get('salePrice') or
                                 item.get('price') or item.get('sellPrice') or 0)
                    if price_val: result['price'] = _safe_int(price_val)

                    # 이미지: 여러 키 시도
                    for img_key in ['listImageUrl','frontImageUrl','mainImageUrl','imageUrl','image']:
                        v = item.get(img_key,'')
                        if v: result['image_url'] = v; break

                    # 원단 정보: frontDetail, productInfo, materialInfo 등
                    for detail_key in ['frontDetail','detailContent','productInfo','materialInfo','itemInfo','description']:
                        detail_html = item.get(detail_key,'')
                        if detail_html:
                            detail_text = BeautifulSoup(str(detail_html), 'html.parser').get_text(' ')
                            fab = _extract_fabric(detail_text)
                            if fab['composition'] or fab['material']:
                                result['fabric'] = fab
                                result['season'] = result['season'] or _extract_season(detail_text)
                                break

                    # 시즌 태그 별도 필드
                    for sk in ['season','seasonCode','tags']:
                        v = item.get(sk,'')
                        if v and isinstance(v, str):
                            s = _extract_season(v) or v.upper()
                            if s: result['season'] = s; break
            except Exception as e:
                result['error'] = f'__NEXT_DATA__ 파싱 오류: {e}'

        # ── 2순위: og: 메타 태그 ──
        if not result['name']:
            og = soup.find('meta', property='og:title')
            if og: result['name'] = og.get('content','').strip()
        if not result['image_url']:
            og = soup.find('meta', property='og:image')
            if og: result['image_url'] = og.get('content','')
        if not result['price']:
            og = soup.find('meta', property='product:price:amount')
            if og:
                result['price'] = _safe_int(og.get('content','0'))
        if not result['brand']:
            og = soup.find('meta', property='product:brand')
            if og: result['brand'] = og.get('content','')

        # ── 3순위: 전체 텍스트에서 원단·시즌 추출 ──
        if not result['fabric']['composition']:
            fab = _extract_fabric(page_text)
            if fab['composition'] or fab['material']:
                result['fabric'] = fab
        if not result['season']:
            result['season'] = _extract_season(page_text)

        # ── 가격 텍스트 fallback ──
        if not result['price']:
            for m in re.finditer(r'[\d,]{5,}', page_text):
                v = _safe_int(m.group())
                if 5000 <= v <= 5000000:
                    result['price'] = v; break

        result['success'] = True

    except requests.Timeout:
        result['error'] = '타임아웃 (사이트 응답 없음)'
    except requests.ConnectionError as e:
        result['error'] = f'연결 오류: {e}'
    except Exception as e:
        result['error'] = str(e)

    return result


# ══════════════════════════════════════════════════════════════════
#  W컨셉 requests fallback
# ══════════════════════════════════════════════════════════════════

def _crawl_wconcept_requests(url: str) -> dict:
    result = {
        'success': False, 'name':'', 'price':0, 'image_url':'', 'brand':'',
        'fabric':{'material':'','composition':'','weight':'','origin':''},
        'season':'', 'error':''
    }
    sess = make_session()
    try:
        try: sess.get('https://www.wconcept.co.kr/', timeout=8)
        except: pass
        human_delay(0.6, 1.5)
        sess.headers.update({'Referer': 'https://www.wconcept.co.kr/', 'User-Agent': _ua()})

        resp = sess.get(url, timeout=15)
        if resp.status_code != 200:
            result['error'] = f'HTTP {resp.status_code}'
            return result

        soup = BeautifulSoup(resp.text, 'html.parser')
        page_text = soup.get_text(' ', strip=True)

        # ── __NEXT_DATA__ ──
        nd_script = soup.find('script', id='__NEXT_DATA__')
        if nd_script:
            try:
                nd = json.loads(nd_script.string or '{}')
                pp = nd.get('props',{}).get('pageProps',{})
                item = (pp.get('product') or pp.get('item') or
                        pp.get('productDetail') or pp.get('data') or {})
                if not item and 'dehydratedState' in pp:
                    queries = pp['dehydratedState'].get('queries', [])
                    for q in queries:
                        qdata = q.get('state',{}).get('data',{})
                        if isinstance(qdata, dict) and (qdata.get('productName') or qdata.get('name')):
                            item = qdata; break

                if item:
                    result['name'] = (item.get('productName') or item.get('itemName') or
                                      item.get('name') or '')
                    result['brand'] = (item.get('brandName') or item.get('brand') or '')
                    price_val = (item.get('salePrice') or item.get('consumerPrice') or
                                 item.get('price') or 0)
                    if price_val: result['price'] = _safe_int(price_val)

                    for img_key in ['mainImageUrl','listImageUrl','frontImageUrl','imageUrl','image']:
                        v = item.get(img_key,'')
                        if v: result['image_url'] = v; break

                    for detail_key in ['detailContent','productInfo','materialInfo','description','content']:
                        detail_html = item.get(detail_key,'')
                        if detail_html:
                            detail_text = BeautifulSoup(str(detail_html), 'html.parser').get_text(' ')
                            fab = _extract_fabric(detail_text)
                            if fab['composition'] or fab['material']:
                                result['fabric'] = fab
                                result['season'] = result['season'] or _extract_season(detail_text)
                                break
            except Exception as e:
                pass  # og: fallback으로 진행

        # og: 메타 fallback
        if not result['name']:
            og = soup.find('meta', property='og:title')
            if og: result['name'] = og.get('content','').strip()
        if not result['image_url']:
            og = soup.find('meta', property='og:image')
            if og: result['image_url'] = og.get('content','')
        if not result['price']:
            for el in soup.find_all(class_=re.compile(r'price', re.I)):
                nums = re.findall(r'[\d,]+', el.get_text())
                for n in nums:
                    v = _safe_int(n)
                    if 5000 <= v <= 5000000:
                        result['price'] = v; break
                if result['price']: break

        if not result['fabric']['composition']:
            fab = _extract_fabric(page_text)
            if fab['composition'] or fab['material']:
                result['fabric'] = fab
        if not result['season']:
            result['season'] = _extract_season(page_text)
        if not result['price']:
            for m in re.finditer(r'[\d,]{5,}', page_text):
                v = _safe_int(m.group())
                if 5000 <= v <= 5000000:
                    result['price'] = v; break

        result['success'] = True

    except requests.Timeout:
        result['error'] = '타임아웃'
    except requests.ConnectionError as e:
        result['error'] = f'연결 오류: {e}'
    except Exception as e:
        result['error'] = str(e)

    return result


# ══════════════════════════════════════════════════════════════════
#  네이버 블로그 수 → Playwright 버전으로 위임
# ══════════════════════════════════════════════════════════════════

def crawl_naver_blog_count(query: str, client_id: str='', client_secret: str='') -> int:
    try:
        from crawler.playwright_crawl import crawl_naver_blog_count_pw
        return crawl_naver_blog_count_pw(query, client_id, client_secret)
    except Exception:
        pass
    # requests fallback
    try:
        sess = make_session()
        r = sess.get(
            f'https://search.naver.com/search.naver?where=blog&query={quote(query)}',
            timeout=10
        )
        if r.status_code == 200:
            for pat in [r'"totalCount"\s*:\s*(\d+)', r'총\s*<[^>]*>\s*([\d,]+)']:
                m = re.search(pat, r.text)
                if m: return int(m.group(1).replace(',',''))
    except: pass
    return 0


# ══════════════════════════════════════════════════════════════════
#  인스타그램 언급량 → Playwright 버전으로 위임
# ══════════════════════════════════════════════════════════════════

def crawl_instagram_hashtag(keyword: str) -> int:
    try:
        from crawler.playwright_crawl import crawl_instagram_count_pw
        r = crawl_instagram_count_pw(keyword)
        return r.get('count', 0)
    except Exception:
        pass
    return 0


# ── 카테고리 URL 매핑 ─────────────────────────────────────────────
CATEGORY_29CM = {'denim':'1057','shirt':'1045','tshirt':'1039'}
CATEGORY_WCONCEPT = {'denim':'bottom-denim','shirt':'top-shirt','tshirt':'top-tshirt'}
