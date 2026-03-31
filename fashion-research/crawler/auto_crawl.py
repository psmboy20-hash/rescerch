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
    # requests 우선 사용 (playwright는 서버 환경에서 hang 발생)
    d = _crawl_29cm_requests(url)
    if d.get('success'):
        return d
    # requests 실패 시에만 playwright 시도 (3초 타임아웃)
    try:
        import signal
        def _timeout_handler(signum, frame):
            raise TimeoutError('playwright timeout')
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(30)
        try:
            from crawler.playwright_crawl import crawl_29cm_product as _pw
            result = _pw(url)
        finally:
            signal.alarm(0)
        return result
    except Exception:
        pass
    return d  # requests 결과 반환 (실패여도)

def crawl_wconcept_product(url: str) -> dict:
    # requests 우선 사용 (playwright는 서버 환경에서 hang 발생)
    d = _crawl_wconcept_requests(url)
    if d.get('success'):
        return d
    # requests 실패 시에만 playwright 시도 (30초 타임아웃)
    try:
        import signal
        def _timeout_handler(signum, frame):
            raise TimeoutError('playwright timeout')
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(30)
        try:
            from crawler.playwright_crawl import crawl_wconcept_product as _pw
            result = _pw(url)
        finally:
            signal.alarm(0)
        return result
    except Exception:
        pass
    return d  # requests 결과 반환 (실패여도)

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
        raw_text = resp.text

        # ── 0순위: __next_f 청크 파싱 (Next.js App Router 방식) ──
        # 29cm은 __NEXT_DATA__ 대신 self.__next_f.push 방식으로 데이터 전달
        try:
            chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', raw_text, re.DOTALL)
            full_nf = ''
            for chunk in chunks:
                try:
                    full_nf += json.loads(f'"{chunk}"')
                except:
                    full_nf += chunk

            if full_nf:
                # 브랜드: schema.org Brand
                bm = re.search(r'"brand":\{"@type":"Brand"[^}]*?"name":"([^"]+)"', full_nf)
                if bm: result['brand'] = bm.group(1)

                # 가격: schema.org Offer
                pm = re.search(r'"offers":\{"@type":"Offer","price":(\d+)', full_nf)
                if pm: result['price'] = int(pm.group(1))

                # 이미지
                im = re.search(r'"image":"(https://[^"]+(?:jpg|jpeg|png|webp)[^"]*)"', full_nf)
                if im: result['image_url'] = im.group(1)

                # 상품명: description 메타 (브랜드 제거)
                nm = re.search(r'"description","content":"([^"]+)"', full_nf)
                if nm:
                    name_raw = nm.group(1)
                    # "브랜드(EN) 제품명" → 제품명만 추출
                    name_clean = re.sub(r'^[^)]+\)\s*', '', name_raw).strip()
                    result['name'] = name_clean if name_clean else name_raw

                # itemDetails: 소재, 제조국, 제조연월 등
                all_details = re.findall(
                    r'"itemDetailsTitles":"([^"]+)","itemDetailsValue":"([^"]+)"', full_nf
                )
                details_map = {}
                for k, v in all_details:
                    details_map[k] = v  # 중복 시 마지막 값 사용

                # 소재 (composition)
                composition = (details_map.get('제품 소재') or details_map.get('소재') or
                               details_map.get('혼용률') or '')
                if composition:
                    result['fabric']['composition'] = composition
                    # material 추론 (cotton, denim, linen 등)
                    mat_m = re.search(r'(COTTON|DENIM|LINEN|POLYESTER|WOOL|SILK|NYLON|RAYON|TENCEL|MODAL)',
                                      composition.upper())
                    if mat_m:
                        result['fabric']['material'] = mat_m.group(1).capitalize()

                # 제조국
                origin = details_map.get('제조국', '')
                if origin: result['fabric']['origin'] = origin

                # 제조연월: "202303" → "2023.03"
                mfg_raw = details_map.get('제조연월', '')
                if mfg_raw:
                    mfg_m2 = re.match(r'(\d{4})(\d{2})', mfg_raw)
                    if mfg_m2:
                        result['mfg_date'] = f"{mfg_m2.group(1)}.{mfg_m2.group(2)}"

                # 시즌: 제목이나 텍스트에서 SS/FW 패턴
                season_m2 = re.search(r'\b(2[0-9](?:SS|FW|AW|SU|SP))\b', full_nf)
                if season_m2: result['season'] = season_m2.group(1)

        except Exception as e:
            pass  # fallback으로 계속

        # ── 1순위: __NEXT_DATA__ JSON 파싱 (구버전 호환) ──
        if not result['brand'] and not result['price']:
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
                            if isinstance(qdata, dict) and (qdata.get('itemName') or qdata.get('productName')):
                                item = qdata; break
                    if item:
                        if not result['name']:
                            result['name'] = (item.get('itemName') or item.get('productName') or item.get('name',''))
                        if not result['brand']:
                            result['brand'] = (item.get('brandName') or item.get('brand',''))
                        if not result['price']:
                            pv = item.get('consumerPrice') or item.get('salePrice') or item.get('price',0)
                            if pv: result['price'] = _safe_int(pv)
                        for img_key in ['listImageUrl','frontImageUrl','mainImageUrl','imageUrl']:
                            v = item.get(img_key,'')
                            if v and not result['image_url']: result['image_url'] = v; break
                except Exception:
                    pass

        # ── 2순위: og: 메타 태그 ──
        if not result['name']:
            og = soup.find('meta', property='og:title')
            if og: result['name'] = og.get('content','').replace(' - 감도 깊은 취향 셀렉트샵 29CM','').strip()
        if not result['image_url']:
            og = soup.find('meta', property='og:image')
            if og: result['image_url'] = og.get('content','')
        if not result['price']:
            og = soup.find('meta', property='product:price:amount')
            if og: result['price'] = _safe_int(og.get('content','0'))
        if not result['brand']:
            # og:description에서 "브랜드(EN) 제품명" 패턴으로 브랜드 추출
            og_d = soup.find('meta', property='og:description')
            if og_d:
                desc = og_d.get('content','')
                bm2 = re.match(r'^(.+?)\(([A-Z0-9]+)\)\s+', desc)
                if bm2: result['brand'] = bm2.group(1).strip()

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
        raw_text = resp.text

        # ── 존재하지 않는 상품 체크 ──
        if '존재하지 않는 상품' in raw_text or len(raw_text) < 500:
            result['error'] = '존재하지 않는 상품'
            return result

        # ── 0순위: og:description에서 브랜드·제품명 추출 ──
        # W컨셉 패턴: "[브랜드EN 브랜드KO] 제품명 (품번)"
        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            desc = og_desc.get('content', '')
            m = re.match(r'\[([^\]]+)\]\s*(.*)', desc)
            if m:
                brand_raw = m.group(1)  # "jsny 제이에스엔와이"
                prod_name = re.sub(r'\s*\([A-Z0-9\-]+\)\s*$', '', m.group(2)).strip()
                # 한글 브랜드명 우선
                ko_m = re.search(r'[가-힣][가-힣\s]+', brand_raw)
                result['brand'] = ko_m.group().strip() if ko_m else brand_raw.strip()
                result['name'] = prod_name

        # ── 1순위: HTML h2.brand > a 태그에서 브랜드 ──
        if not result['brand']:
            brand_h2 = soup.find('h2', class_='brand')
            if brand_h2:
                a = brand_h2.find('a')
                result['brand'] = a.get_text(strip=True) if a else brand_h2.get_text(strip=True)

        # ── 2순위: og:title에서 제품명 ──
        if not result['name']:
            og_t = soup.find('meta', property='og:title')
            if og_t:
                title = og_t.get('content','').replace('[W CONCEPT]','').strip()
                result['name'] = title

        # ── 3순위: og:image 이미지 ──
        if not result['image_url']:
            og_i = soup.find('meta', property='og:image')
            if og_i: result['image_url'] = og_i.get('content','')

        # ── 4순위: dt/dd 구조에서 가격 추출 ──
        # W컨셉: <dt>정상가</dt><dd><em>399,000</em> 원</dd>
        for dt in soup.find_all('dt'):
            label = dt.get_text(strip=True)
            if label in ['정상가', '판매가']:
                dd = dt.find_next('dd')
                if dd:
                    val = re.sub(r'[^\d]', '', dd.get_text())
                    if val:
                        v = int(val)
                        if 1000 <= v <= 10000000:
                            result['price'] = v
                            break

        # ── 5순위: JSON 인라인 데이터 (brandName 등) ──
        brand_m = re.findall(r'"brandNameKo"\s*:\s*"([^"]+)"', raw_text)
        if brand_m and not result['brand']:
            result['brand'] = brand_m[0]

        # 소재: HTML body text에서 혼용률 패턴
        fabric_pattern = re.findall(
            r'((?:COTTON|POLYESTER|NYLON|WOOL|LINEN|RAYON|SILK|TENCEL|MODAL|ACRYLIC|VISCOSE)'
            r'(?:\s*/\s*(?:COTTON|POLYESTER|NYLON|WOOL|LINEN|RAYON|SILK|TENCEL|MODAL|ACRYLIC|VISCOSE))*'
            r'\s*\d+%(?:\s*,?\s*(?:COTTON|POLYESTER|NYLON|WOOL|LINEN|RAYON|SILK|TENCEL|MODAL|ACRYLIC|VISCOSE)\s*\d+%)*)',
            page_text, re.I
        )
        if fabric_pattern:
            result['fabric']['composition'] = fabric_pattern[0]
            mat_m = re.search(r'(COTTON|DENIM|LINEN|POLYESTER|WOOL|SILK|NYLON|RAYON|TENCEL|MODAL)',
                              fabric_pattern[0].upper())
            if mat_m: result['fabric']['material'] = mat_m.group(1).capitalize()

        # 시즌
        if not result['season']:
            result['season'] = _extract_season(page_text)

        # 가격 최종 fallback
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
    # 1순위: 네이버 공식 API (playwright 제거 - hang 발생)
    if client_id and client_secret:
        try:
            import requests as _req
            r = _req.get(
                'https://openapi.naver.com/v1/search/blog.json',
                params={'query': query, 'display': 1},
                headers={
                    'X-Naver-Client-Id': client_id,
                    'X-Naver-Client-Secret': client_secret
                },
                timeout=8
            )
            d = r.json()
            if 'total' in d:
                return int(d['total'])
        except Exception:
            pass
    # 2순위: requests 크롤링 fallback
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
    # playwright는 서버 환경에서 hang 발생
    # Instagram 분석은 전용 분석 페이지에서 agent로 처리
    # 업데이트 센터에서는 0 반환 (score_instagram은 수동 입력 또는 분석 페이지 이용)
    return 0


# ── 카테고리 URL 매핑 ─────────────────────────────────────────────
CATEGORY_29CM = {'denim':'1057','shirt':'1045','tshirt':'1039'}
CATEGORY_WCONCEPT = {'denim':'bottom-denim','shirt':'top-shirt','tshirt':'top-tshirt'}
