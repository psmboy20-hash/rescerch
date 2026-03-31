"""
W컨셉 제품 정보 크롤러
"""

import requests
import re
import time
import random
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.wconcept.co.kr/",
}


def extract_product_id(url: str) -> str | None:
    """W컨셉 URL에서 Product ID 추출"""
    match = re.search(r'/Product/(\d+)', url)
    if match:
        return match.group(1)
    return None


def fetch_product_info(url: str) -> dict:
    """
    W컨셉 제품 URL에서 제품 정보 파싱

    Returns:
        {
            'success': bool,
            'name': str,
            'price': int,
            'image_url': str,
            'brand': str,
            'error': str
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
        time.sleep(random.uniform(1.0, 2.5))

        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code != 200:
            result['error'] = f'HTTP {resp.status_code}'
            return result

        soup = BeautifulSoup(resp.text, 'html.parser')

        # og 메타태그로 파싱
        og_title = soup.find('meta', property='og:title')
        if og_title:
            result['name'] = og_title.get('content', '').strip()

        og_image = soup.find('meta', property='og:image')
        if og_image:
            result['image_url'] = og_image.get('content', '')

        # 가격 파싱
        price_tag = soup.find(class_=re.compile(r'price|Price', re.I))
        if price_tag:
            price_text = price_tag.get_text(strip=True).replace(',', '')
            nums = re.findall(r'\d+', price_text)
            if nums:
                result['price'] = int(nums[0])

        # 브랜드
        brand_tag = soup.find(class_=re.compile(r'brand|Brand', re.I))
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
    W컨셉 카테고리 페이지에서 랭킹 데이터 가져오기
    """
    items = []

    try:
        time.sleep(random.uniform(1.0, 2.0))
        resp = requests.get(category_url, headers=HEADERS, timeout=10)

        if resp.status_code != 200:
            return items

        soup = BeautifulSoup(resp.text, 'html.parser')

        product_cards = soup.find_all(class_=re.compile(r'prd.*item|item.*prd|goods', re.I))

        for i, card in enumerate(product_cards[:max_items], 1):
            item = {
                'rank': i,
                'product_id': '',
                'name': '',
                'brand': '',
                'price': 0,
                'image_url': ''
            }

            link = card.find('a', href=True)
            if link:
                item['product_id'] = extract_product_id(link['href']) or ''

            name_el = card.find(class_=re.compile(r'name|title', re.I))
            if name_el:
                item['name'] = name_el.get_text(strip=True)

            brand_el = card.find(class_=re.compile(r'brand', re.I))
            if brand_el:
                item['brand'] = brand_el.get_text(strip=True)

            price_el = card.find(class_=re.compile(r'price', re.I))
            if price_el:
                price_text = price_el.get_text(strip=True).replace(',', '')
                nums = re.findall(r'\d+', price_text)
                if nums:
                    item['price'] = int(nums[0])

            img = card.find('img')
            if img:
                item['image_url'] = img.get('src') or img.get('data-src') or ''

            items.append(item)

    except Exception as e:
        print(f"[W컨셉 크롤링 오류] {e}")

    return items


# 카테고리별 URL 매핑
CATEGORY_URLS = {
    'denim': 'https://www.wconcept.co.kr/category/bottom-denim',
    'shirt': 'https://www.wconcept.co.kr/category/top-shirt',
    'tshirt': 'https://www.wconcept.co.kr/category/top-tshirt',
}
