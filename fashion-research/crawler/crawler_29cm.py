"""
29cm 제품 정보 크롤러
- 제품 URL에서 이름, 가격, 이미지, 판매 순위 정보 파싱
- 봇 차단 우회를 위한 User-Agent 설정
"""

import requests
import re
import time
import random
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.29cm.co.kr/",
}

def extract_product_no(url: str) -> str | None:
    """URL에서 productNo 추출"""
    match = re.search(r'productNo=(\d+)', url)
    if match:
        return match.group(1)
    return None


def fetch_product_info(url: str) -> dict:
    """
    29cm 제품 URL에서 제품 정보 파싱

    Returns:
        {
            'success': bool,
            'name': str,
            'price': int,
            'image_url': str,
            'brand': str,
            'error': str (if failed)
        }
    """
    result = {
        'success': False,
        'name': '',
        'price': 0,
        'image_url': '',
        'brand': '',
        'error': ''
    }

    try:
        # 랜덤 딜레이 (봇 차단 방지)
        time.sleep(random.uniform(1.0, 2.5))

        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code != 200:
            result['error'] = f'HTTP {resp.status_code}'
            return result

        soup = BeautifulSoup(resp.text, 'html.parser')

        # 제품명 파싱
        name_tag = soup.find('h1', class_=re.compile(r'product.*name|name.*product', re.I))
        if not name_tag:
            name_tag = soup.find('meta', property='og:title')
            if name_tag:
                result['name'] = name_tag.get('content', '').strip()
        else:
            result['name'] = name_tag.get_text(strip=True)

        # 가격 파싱
        price_tag = soup.find(class_=re.compile(r'price', re.I))
        if price_tag:
            price_text = price_tag.get_text(strip=True)
            price_numbers = re.findall(r'\d+', price_text.replace(',', ''))
            if price_numbers:
                result['price'] = int(price_numbers[0])

        # 이미지 파싱
        img_tag = soup.find('meta', property='og:image')
        if img_tag:
            result['image_url'] = img_tag.get('content', '')

        # 브랜드명
        brand_tag = soup.find(class_=re.compile(r'brand', re.I))
        if brand_tag:
            result['brand'] = brand_tag.get_text(strip=True)

        result['success'] = True

    except requests.Timeout:
        result['error'] = '요청 시간 초과'
    except requests.ConnectionError:
        result['error'] = '연결 오류'
    except Exception as e:
        result['error'] = str(e)

    return result


def get_category_ranking(category_url: str, max_items: int = 50) -> list:
    """
    29cm 카테고리 페이지에서 랭킹 데이터 가져오기

    Returns:
        [{'rank': int, 'product_no': str, 'name': str, 'brand': str, 'price': int, 'image_url': str}]
    """
    items = []

    try:
        time.sleep(random.uniform(1.0, 2.0))
        resp = requests.get(category_url, headers=HEADERS, timeout=10)

        if resp.status_code != 200:
            return items

        soup = BeautifulSoup(resp.text, 'html.parser')

        # 제품 카드 파싱 (실제 클래스명은 사이트마다 다를 수 있음)
        product_cards = soup.find_all(class_=re.compile(r'product.*item|item.*product', re.I))

        for i, card in enumerate(product_cards[:max_items], 1):
            item = {
                'rank': i,
                'product_no': '',
                'name': '',
                'brand': '',
                'price': 0,
                'image_url': ''
            }

            # 링크에서 product_no 추출
            link = card.find('a', href=True)
            if link:
                item['product_no'] = extract_product_no(link['href']) or ''

            # 제품명
            name_el = card.find(class_=re.compile(r'name', re.I))
            if name_el:
                item['name'] = name_el.get_text(strip=True)

            # 브랜드
            brand_el = card.find(class_=re.compile(r'brand', re.I))
            if brand_el:
                item['brand'] = brand_el.get_text(strip=True)

            # 가격
            price_el = card.find(class_=re.compile(r'price', re.I))
            if price_el:
                price_text = price_el.get_text(strip=True).replace(',', '')
                nums = re.findall(r'\d+', price_text)
                if nums:
                    item['price'] = int(nums[0])

            # 이미지
            img = card.find('img')
            if img:
                item['image_url'] = img.get('src') or img.get('data-src') or ''

            items.append(item)

    except Exception as e:
        print(f"[29cm 크롤링 오류] {e}")

    return items


# 카테고리별 URL 매핑
CATEGORY_URLS = {
    'denim': 'https://www.29cm.co.kr/categories/1057',       # 데님팬츠
    'shirt': 'https://www.29cm.co.kr/categories/1045',       # 셔츠/블라우스
    'tshirt': 'https://www.29cm.co.kr/categories/1039',      # 반팔티/나시
}
