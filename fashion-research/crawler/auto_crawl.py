"""
패션 리서치 자동 크롤러 v4
- __NEXT_DATA__ JSON 우선 파싱 (29cm, W컨셉 모두 Next.js SPA)
- og: 메타 태그 fallback
- 소재·혼용률·원산지·시즌 정규식 추출
- 상세페이지 이미지 OCR (Tesseract) - 소재·사이즈스펙·제조년월 추출
- 시즌 자동 추론 (제조년월/등록일 기반 SS/FW)
- 리뷰 수 JSON-LD에서 추출
- 네이버 블로그 API + 웹 fallback
"""

import requests, re, time, random, json, io, os
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

# ── OCR 유틸 ─────────────────────────────────────────────────────────
def _ocr_image_bytes(img_bytes: bytes) -> str:
    """이미지 바이트에서 OCR로 텍스트 추출 (Tesseract 한국어+영어)"""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        img = img.convert('L')  # 흑백 변환으로 OCR 정확도 향상
        text = pytesseract.image_to_string(img, lang='kor+eng')
        return text
    except Exception:
        return ''

def _download_img(sess, url: str) -> bytes:
    """이미지 다운로드 (?width=800 파라미터 사용)"""
    try:
        img_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.29cm.co.kr/',
            'Accept': 'image/*,*/*',
        }
        full_url = url if '?' in url else url + '?width=800'
        r = sess.get(full_url, headers=img_headers, timeout=10)
        if r.content[:3] == b'\xff\xd8\xff':  # JPEG 시그니처 확인
            return r.content
    except Exception:
        pass
    return b''

# ── OCR 결과 파싱 ────────────────────────────────────────────────────
def _parse_ocr_product_guide(ocr_text: str) -> dict:
    """Product Guide 이미지 OCR 결과에서 소재/사이즈/제조년월 추출"""
    result = {'composition': '', 'material': '', 'size_spec': '', 'mfg_date': '', 'origin': ''}
    if not ocr_text:
        return result

    lines = ocr_text.replace('\r', '').split('\n')
    full_text = ocr_text

    for i, line in enumerate(lines):
        line_s = line.strip()

        # ① Fabric/소재 라인 - "Shell : Cotton 100%" 형태 우선 처리
        if re.search(r'Fabric|소재|원단|FABRIC|MATERIAL|Material', line_s, re.I):
            # 같은 줄 + 다음 줄 합쳐서 탐색
            target = line_s + ' ' + (lines[i+1].strip() if i+1 < len(lines) else '')
            # "Shell : Cotton 100%" 또는 "Cotton 100%" 패턴
            comp_m = re.search(
                r'(?:Shell|Body|겉감)?\s*[:\-]?\s*'
                r'((?:Cotton|Wool|Polyester|Nylon|Linen|Silk|Rayon|Tencel|Modal|Acrylic|Cashmere|Viscose|면|울|폴리|나일론|린넨|레이온)'
                r'(?:[^\n]{0,30}\d+%(?:[,/·\s]+[A-Za-z가-힣]+\s*\d+%)*)?)',
                target, re.I
            )
            if comp_m:
                raw = comp_m.group(1).strip()
                # 접두사 제거 및 정제
                raw = re.sub(r'^(Shell|Body|Fabric|소재|겉감)\s*[:\-]?\s*', '', raw, flags=re.I).strip()
                # 순수 혼용률만 저장: 퍼센트(%) 포함 또는 간단한 소재명만
                # 마케팅 설명문 제외 (50자 초과이고 % 없으면 무시)
                if '%' in raw or len(raw) <= 40:
                    result['composition'] = raw[:80]
                    mat_m = re.search(
                        r'(Cotton|Denim|Linen|Polyester|Wool|Silk|Nylon|Rayon|Tencel|Modal|Cashmere)',
                        raw, re.I
                    )
                    if mat_m:
                        result['material'] = mat_m.group(1).capitalize()

        # ② Size 라인 (사이즈 스펙) - "Free : 총장 69cm ..." 형태 대응
        # 사이즈 키워드가 있는 라인 직접 탐색 (같은 줄에 cm 포함 가능)
        if re.search(r'총장|어깨넓이|어깨|가슴단면|밑단|암홀|소매', line_s, re.I):
            # cm 수치가 포함된 경우 사이즈 스펙으로 저장
            if re.search(r'\d+\.?\d*\s*cm', line_s, re.I):
                # 다음 줄도 포함 (멀티라인 가능)
                size_part = line_s
                if i+1 < len(lines) and re.search(r'\d+\.?\d*\s*cm', lines[i+1], re.I):
                    size_part += ' / ' + lines[i+1].strip()
                # "Free :" 또는 사이즈명 앞 부분 정제
                size_part = re.sub(r'^(Free|S|M|L|XL|XXL|One Size|OS)\s*[:\-]?\s*', r'\1 - ', size_part, flags=re.I)
                result['size_spec'] = size_part[:200]
        elif re.search(r'^Size|^사이즈|^SIZE', line_s, re.I):
            size_lines = []
            for j in range(i, min(i+6, len(lines))):
                sl = lines[j].strip()
                if re.search(r'\d+\.?\d*\s*cm', sl, re.I):
                    size_lines.append(sl)
            if size_lines:
                result['size_spec'] = ' / '.join(size_lines)[:200]

        # ③ 제조년월
        mfg_m = re.search(r'(?:제조년월|제조연월|Manufacture|MFG)[^\n]*?[:\-]?\s*(\d{4}[./년]\d{2}|\d{6})', line_s, re.I)
        if mfg_m:
            raw_mfg = mfg_m.group(1)
            m6 = re.match(r'(\d{4})(\d{2})$', raw_mfg)
            if m6:
                result['mfg_date'] = f"{m6.group(1)}.{m6.group(2)}"
            else:
                result['mfg_date'] = raw_mfg.replace('년', '.').replace('/', '.')

        # ④ 원산지
        if re.search(r'(?:Made in|제조국|원산지|Country)', line_s, re.I):
            origin_m = re.search(
                r'(?:Made in|제조국|원산지|Country)[^\n]*?[:\-]?\s*([A-Za-z가-힣]+(?:\s+[A-Za-z가-힣]+)?)',
                line_s, re.I
            )
            if origin_m:
                result['origin'] = origin_m.group(1).strip()

    # ⑤ 전체 텍스트에서 혼용률 패턴 보조 탐색 (라인별 탐색에서 못 찾은 경우)
    if not result['composition']:
        # "Cotton 100%" 또는 "COTTON 100%" 단순 패턴
        comp_short = re.search(
            r'((?:Cotton|Wool|Polyester|Nylon|Linen|Silk|Rayon|Tencel|Modal|Cashmere|Acrylic|Viscose)'
            r'\s*\d+%(?:[,/·\s]+(?:Cotton|Wool|Polyester|Nylon|Linen|Silk|Rayon|Tencel|Modal|Cashmere|Acrylic|Viscose)\s*\d+%)*)',
            full_text, re.I
        )
        if comp_short:
            result['composition'] = comp_short.group(1).strip()[:80]
            mat_m = re.search(
                r'(Cotton|Denim|Linen|Polyester|Wool|Silk|Nylon|Rayon|Tencel|Modal)',
                result['composition'], re.I
            )
            if mat_m:
                result['material'] = mat_m.group(1).capitalize()

    return result


def _clean_ocr_size_spec(text: str) -> str:
    """사이즈 스펙 OCR 오류 후처리
    - '55077' -> '55cm' (숫자+큰숫자 노이즈 제거)
    - '5567'  -> '55cm' (앞 2자리만 유효 처리)
    - 'em' -> 'cm' (오타정정)
    """
    if not text:
        return text
    # 'em' -> 'cm' OCR 오타 (점 포함)
    text = re.sub(r'(?<=[0-9])\.?em\b', 'cm', text)
    # 숫자+숫자(2자리 이상) 노이즈 제거: 앞 2자리만 유효로 취급
    # '55077' -> '55cm', '5567' -> '55cm'
    text = re.sub(r'(\d{2})\s*(\d{2,})(?=\s|/|$|단|단면|\b)', lambda m: m.group(1)+'cm', text)
    return text.strip()

# ── 시즌 자동 추론 ───────────────────────────────────────────────────
def _infer_season_from_date(date_str: str) -> str:
    """날짜 문자열(YYYY-MM-DD 또는 YYYY.MM 또는 YYYYMM)에서 SS/FW 추론
    SS: 2월~7월, FW: 8월~1월
    """
    if not date_str:
        return ''
    m = re.search(r'(\d{4})[./\-](\d{1,2})', date_str)
    if not m:
        m = re.match(r'(\d{4})(\d{2})', date_str)
    if not m:
        return ''
    year = int(m.group(1))
    month = int(m.group(2))
    if 2 <= month <= 7:
        return f"{year}SS"
    elif month >= 8:
        return f"{year}FW"
    else:  # 1월은 전년도 FW
        return f"{year-1}FW"

# ── 텍스트에서 원단 정보 추출 ──────────────────────────────────────
def _extract_fabric(text: str) -> dict:
    fab = {'material':'', 'composition':'', 'weight':'', 'origin':''}

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

    m = re.search(r'원산지\s*[:\-]?\s*([가-힣a-zA-Z\s]+?)(?:\n|,|\.|·)', text)
    if m: fab['origin'] = m.group(1).strip()

    m = re.search(r'(\d+\s*(?:oz|g/m²|수))', text, re.IGNORECASE)
    if m: fab['weight'] = m.group(1).strip()

    return fab

def _extract_season(text: str) -> str:
    m = re.search(r'\b((?:SS|FW|AW|RE|PF|PRE)\s*(?:20)?\d{2})\b', text, re.IGNORECASE)
    if m: return m.group(1).upper().replace(' ','')
    return ''

# ══════════════════════════════════════════════════════════════════
#  29cm 크롤러
# ══════════════════════════════════════════════════════════════════

def crawl_29cm_product(url: str) -> dict:
    # requests 우선 사용 (playwright는 서버 환경에서 hang 발생)
    d = _crawl_29cm_requests(url)
    if d.get('success'):
        return d
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
    return d

def crawl_wconcept_product(url: str) -> dict:
    d = _crawl_wconcept_requests(url)
    if d.get('success'):
        return d
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
    return d


def _crawl_29cm_requests(url: str) -> dict:
    result = {
        'success': False, 'name':'', 'price':0, 'image_url':'', 'brand':'',
        'fabric':{'material':'','composition':'','weight':'','origin':''},
        'season':'', 'mfg_date':'', 'size_spec':'', 'review_count':0, 'error':''
    }
    sess = make_session()
    try:
        try: sess.get('https://www.29cm.co.kr/', timeout=8)
        except: pass
        human_delay(0.5, 1.2)
        sess.headers.update({'Referer': 'https://www.29cm.co.kr/', 'User-Agent': _ua()})

        resp = sess.get(url, timeout=15)
        if resp.status_code != 200:
            result['error'] = f'HTTP {resp.status_code}'
            return result

        soup = BeautifulSoup(resp.text, 'html.parser')
        all_scripts = soup.find_all('script')

        # ── 1순위: JSON-LD - 브랜드·가격·이름·이미지·리뷰수 ──
        avail_begin = ''
        for ld_script in soup.find_all('script', type='application/ld+json'):
            try:
                ld = json.loads(ld_script.string or '{}')
                if ld.get('@type') == 'Product':
                    if not result['name']:
                        result['name'] = ld.get('name', '')
                    brand_obj = ld.get('brand', {})
                    if not result['brand'] and isinstance(brand_obj, dict):
                        result['brand'] = brand_obj.get('name', '')
                    offers = ld.get('offers', {})
                    if not result['price'] and isinstance(offers, dict):
                        result['price'] = int(offers.get('price', 0) or 0)
                    img_list = ld.get('image', [])
                    if not result['image_url'] and img_list:
                        first = img_list[0] if isinstance(img_list, list) else img_list
                        if isinstance(first, dict):
                            result['image_url'] = first.get('contentUrl', '')
                        elif isinstance(first, str):
                            result['image_url'] = first
                    # 리뷰 수
                    agg = ld.get('aggregateRating', {})
                    if isinstance(agg, dict) and agg.get('reviewCount'):
                        result['review_count'] = int(agg.get('reviewCount', 0))
                    break
            except Exception:
                pass

        if not result['image_url']:
            og_img = soup.find('meta', property='og:image')
            if og_img: result['image_url'] = og_img.get('content', '')

        # ── 2순위: __next_f 데이터에서 itemDetails + totalCount 파싱 ──
        for s in all_scripts:
            c = s.string or ''
            if 'itemDetailsTitles' not in c and 'availableBeginTimestamp' not in c:
                continue
            normalized = c.replace(chr(92)+chr(34), chr(34))

            # itemDetails 파싱
            if 'itemDetailsTitles' in c:
                details_map = {}
                for m in re.finditer(
                    r'"itemDetailsTitles"\s*:\s*"([^"]+)"[^}]*?"itemDetailsValue"\s*:\s*"([^"]*)"',
                    normalized
                ):
                    details_map[m.group(1).strip()] = m.group(2).strip()

                if details_map:
                    # 소재/혼용률 ("상세페이지 참조" 제외)
                    composition = (details_map.get('제품 소재') or details_map.get('소재') or
                                   details_map.get('혼용률') or details_map.get('섬유의 조성 또는 혼용률') or '')
                    if composition and '상세페이지' not in composition:
                        result['fabric']['composition'] = composition
                        mat_m = re.search(
                            r'(COTTON|DENIM|LINEN|POLYESTER|WOOL|SILK|NYLON|RAYON|TENCEL|MODAL|CASHMERE|ACRYLIC)',
                            composition.upper()
                        )
                        if mat_m:
                            result['fabric']['material'] = mat_m.group(1).capitalize()

                    # 원산지
                    origin = (details_map.get('제조국') or details_map.get('원산지') or
                              details_map.get('제조국(원산지)') or '')
                    if origin and '상세페이지' not in origin:
                        result['fabric']['origin'] = origin

                    # 제조연월
                    mfg_raw = details_map.get('제조연월', '')
                    if mfg_raw and '상세페이지' not in mfg_raw:
                        mfg_m = re.match(r'(\d{4})(\d{2})', mfg_raw)
                        if mfg_m:
                            result['mfg_date'] = f"{mfg_m.group(1)}.{mfg_m.group(2)}"

            # 리뷰 수 보완 (totalCount)
            if not result['review_count']:
                tc_m = re.search(r'"totalCount"\s*:\s*(\d+)', normalized)
                if tc_m:
                    result['review_count'] = int(tc_m.group(1))

            # 상품 등록일 (시즌 추론용) - 다양한 JSON 형식 대응
            if not avail_begin:
                # 형식1: "availableBeginTimestamp":"2024-06-13"
                ab_m = re.search(r'availableBeginTimestamp[":\s]+"(\d{4}-\d{2}-\d{2})', normalized)
                if ab_m:
                    avail_begin = ab_m.group(1).strip()
            if not avail_begin:
                # 형식2: availableBeginTimestamp가 숫자(Unix timestamp)인 경우
                ab_m = re.search(r'availableBeginTimestamp[":\s]+(\d{13,})', normalized)
                if ab_m:
                    try:
                        ts = int(ab_m.group(1)) // 1000
                        from datetime import datetime as _dt
                        avail_begin = _dt.fromtimestamp(ts).strftime('%Y-%m-%d')
                    except Exception:
                        pass
            if not avail_begin:
                # 형식3: availableBeginTimestamp가 YYYY.MM.DD 또는 YYYY/MM/DD
                ab_m = re.search(r'availableBeginTimestamp[^\d]+(\d{4}[./]\d{2}[./]\d{2})', normalized)
                if ab_m:
                    avail_begin = ab_m.group(1).replace('.', '-').replace('/', '-')[:10]

        # ── 3순위: OCR - 상세 이미지에서 소재·사이즈스펙·제조년월 추출 ──
        # "상세페이지 참조"로 텍스트 데이터가 없는 경우 이미지 OCR로 보완
        needs_ocr = (not result['fabric']['composition'] or
                     not result['mfg_date'] or
                     not result['size_spec'])

        if needs_ocr:
            all_text = ' '.join([s.string or '' for s in all_scripts])
            item_paths = re.findall(r'/item/\d{6}/[a-f0-9_]+\.jpg', all_text)
            unique_paths = list(dict.fromkeys(item_paths))
            detail_img_urls = [f'https://img.29cm.co.kr{p}' for p in unique_paths]

            # OCR 결과 누적 (1단계: Product Guide 이미지 우선, 2단계: 나머지)
            ocr_results_priority = []   # Product Guide 확인된 이미지
            ocr_results_fallback = []   # 기타 소재/사이즈 언급 이미지

            for img_url in detail_img_urls[:16]:  # 최대 16개 시도
                img_bytes = _download_img(sess, img_url)
                if not img_bytes or len(img_bytes) > 300000:
                    continue
                ocr_text = _ocr_image_bytes(img_bytes)
                if not ocr_text.strip():
                    continue

                # Product Guide 이미지 (소재+사이즈 모두 있는 이미지) 최우선
                is_product_guide = bool(re.search(
                    r'Product Guide|product guide|프로덕트 가이드', ocr_text, re.I
                ))
                has_fabric = bool(re.search(
                    r'Fabric|Shell\s*:|Cotton|Wool|Polyester|Linen|Silk|Nylon|Rayon|소재|혼용', ocr_text, re.I
                ))
                has_size = bool(re.search(
                    r'총장|어깨|가슴단면|밑단|암홀|소매|Size|사이즈', ocr_text, re.I
                ))

                if is_product_guide or (has_fabric and has_size):
                    ocr_results_priority.append(ocr_text)
                elif has_fabric or has_size:
                    ocr_results_fallback.append(ocr_text)

            # 우선순위 순서로 파싱 적용
            for ocr_text in (ocr_results_priority + ocr_results_fallback):
                ocr_data = _parse_ocr_product_guide(ocr_text)

                if not result['fabric']['composition'] and ocr_data.get('composition'):
                    result['fabric']['composition'] = ocr_data['composition']
                if not result['fabric']['material'] and ocr_data.get('material'):
                    result['fabric']['material'] = ocr_data['material']
                if not result['fabric']['origin'] and ocr_data.get('origin'):
                    result['fabric']['origin'] = ocr_data['origin']
                if not result['mfg_date'] and ocr_data.get('mfg_date'):
                    result['mfg_date'] = ocr_data['mfg_date']
                if not result['size_spec'] and ocr_data.get('size_spec'):
                    result['size_spec'] = _clean_ocr_size_spec(ocr_data['size_spec'])

                # 모든 필드가 채워지면 OCR 종료
                if (result['fabric']['composition'] and result['size_spec']):
                    break

        # ── 4순위: 시즌 추론 ──
        page_text = soup.get_text(' ', strip=True)
        if not result['season']:
            result['season'] = _extract_season(page_text)

        if not result['season'] and result['mfg_date']:
            result['season'] = _infer_season_from_date(result['mfg_date'])

        if not result['season']:
            if avail_begin:
                result['season'] = _infer_season_from_date(avail_begin)
            else:
                # 스크립트에서 재탐색 (더 넓은 패턴)
                for s in all_scripts:
                    c = s.string or ''
                    ab_m = re.search(r'availableBeginTimestamp[^\d]+(\d{4}[-/.]\d{2}[-/.]\d{2})', c)
                    if ab_m:
                        result['season'] = _infer_season_from_date(ab_m.group(1))
                        avail_begin = ab_m.group(1)
                        break

        # ── 이미지 폴더 날짜에서 시즌 보조 추론 (마지막 수단) ──
        # 이미지 경로 /item/YYYYMM/ 에서 최초 등록월 추정
        if not result['season'] and not avail_begin:
            all_text_local = ' '.join([s.string or '' for s in all_scripts])
            folder_dates = re.findall(r'/item/(\d{6})/', all_text_local)
            if folder_dates:
                # 가장 오래된 이미지 폴더 날짜 사용 (최초 등록 추정)
                earliest = sorted(folder_dates)[0]
                try:
                    folder_year = int(earliest[:4])
                    folder_month = int(earliest[4:6])
                    folder_date_str = f"{folder_year}-{folder_month:02d}-01"
                    result['season'] = _infer_season_from_date(folder_date_str)
                    if not result['mfg_date']:
                        result['mfg_date'] = f"{folder_year}.{folder_month:02d}"  # 추정값
                except Exception:
                    pass

        # ── 5순위: 소재 텍스트 fallback ──
        if not result['fabric']['composition']:
            fab = _extract_fabric(page_text)
            if fab.get('composition') or fab.get('material'):
                result['fabric'] = fab

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

        if '존재하지 않는 상품' in raw_text or len(raw_text) < 500:
            result['error'] = '존재하지 않는 상품'
            return result

        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            desc = og_desc.get('content', '')
            m = re.match(r'\[([^\]]+)\]\s*(.*)', desc)
            if m:
                brand_raw = m.group(1)
                prod_name = re.sub(r'\s*\([A-Z0-9\-]+\)\s*$', '', m.group(2)).strip()
                ko_m = re.search(r'[가-힣][가-힣\s]+', brand_raw)
                result['brand'] = ko_m.group().strip() if ko_m else brand_raw.strip()
                result['name'] = prod_name

        if not result['brand']:
            brand_h2 = soup.find('h2', class_='brand')
            if brand_h2:
                a = brand_h2.find('a')
                result['brand'] = a.get_text(strip=True) if a else brand_h2.get_text(strip=True)

        if not result['name']:
            og_t = soup.find('meta', property='og:title')
            if og_t:
                title = og_t.get('content','').replace('[W CONCEPT]','').strip()
                result['name'] = title

        if not result['image_url']:
            og_i = soup.find('meta', property='og:image')
            if og_i: result['image_url'] = og_i.get('content','')

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

        brand_m = re.findall(r'"brandNameKo"\s*:\s*"([^"]+)"', raw_text)
        if brand_m and not result['brand']:
            result['brand'] = brand_m[0]

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
#  네이버 블로그 수
# ══════════════════════════════════════════════════════════════════

def crawl_naver_blog_count(query: str, client_id: str='', client_secret: str='') -> int:
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
#  인스타그램
# ══════════════════════════════════════════════════════════════════

def crawl_instagram_hashtag(keyword: str) -> int:
    return 0


# ── 카테고리 URL 매핑 ─────────────────────────────────────────────
CATEGORY_29CM = {'denim':'1057','shirt':'1045','tshirt':'1039'}
CATEGORY_WCONCEPT = {'denim':'bottom-denim','shirt':'top-shirt','tshirt':'top-tshirt'}
