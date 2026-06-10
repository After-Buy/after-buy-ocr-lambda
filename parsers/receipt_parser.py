import re
import logging

logger = logging.getLogger(__name__)

# 날짜 패턴: 2024-09-20, 2024.09.20, 2024/09/20, 2024 09 20
DATE_PATTERNS = [
    re.compile(r"(\d{4})[.\-/\s](\d{1,2})[.\-/\s](\d{1,2})"),
]

# 가격 패턴: 1,550,000원, ₩1,550,000, 1550000, 1,550,000
PRICE_PATTERNS = [
    re.compile(r"[₩\\]?\s*([\d,]+)\s*원?"),
    re.compile(r"합계\s*[:\s]*([\d,]+)"),
    re.compile(r"총\s*[:\s]*([\d,]+)원?"),
    re.compile(r"TOTAL\s*[:\s]*([\d,]+)", re.IGNORECASE),
]

# 가격 필터링용 불용어 (배송비 등 제외)
PRICE_EXCLUDE_KEYWORDS = ["배송", "적립", "포인트", "할인", "쿠폰", "부가세"]


def parse_receipt(lines: list[str]) -> dict | None:
    """
    영수증 OCR 텍스트에서 구매일, 구매가격, 구매처를 추출.

    Args:
        lines: Textract에서 추출한 텍스트 라인 리스트

    Returns:
        {"purchase_date": str, "purchase_price": int, "purchase_store": str} 또는 None
    """
    if not lines:
        return None

    purchase_date = _extract_date(lines)
    purchase_price = _extract_price(lines)
    purchase_store = _extract_store(lines)

    # 최소 1개 항목은 추출되어야 함
    if not any([purchase_date, purchase_price, purchase_store]):
        logger.warning("영수증에서 어떤 항목도 추출하지 못함")
        return None

    return {
        "purchase_date": purchase_date,
        "purchase_price": purchase_price,
        "purchase_store": purchase_store,
    }


def _extract_date(lines: list[str]) -> str | None:
    """텍스트에서 날짜를 추출하여 YYYY-MM-DD 형식으로 반환."""
    for line in lines:
        for pattern in DATE_PATTERNS:
            match = pattern.search(line)
            if match:
                year, month, day = match.group(1), match.group(2), match.group(3)
                # 유효성 검증
                month_int = int(month)
                day_int = int(day)
                if 1 <= month_int <= 12 and 1 <= day_int <= 31:
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


def _extract_price(lines: list[str]) -> int | None:
    """텍스트에서 가격을 추출. 가장 큰 금액을 구매가격으로 간주."""
    prices = []

    for line in lines:
        # 불용어가 포함된 라인은 스킵
        if any(keyword in line for keyword in PRICE_EXCLUDE_KEYWORDS):
            continue

        for pattern in PRICE_PATTERNS:
            matches = pattern.finditer(line)
            for match in matches:
                price_str = match.group(1).replace(",", "")
                try:
                    price = int(price_str)
                    if price > 0:
                        prices.append(price)
                except ValueError:
                    continue

    if not prices:
        return None

    # 가장 큰 금액을 구매가격으로 반환
    return max(prices)


def _extract_store(lines: list[str]) -> str | None:
    """텍스트에서 구매처(상호명)를 추출. 보통 영수증 상단에 위치."""
    # 알려진 브랜드/매장 키워드
    store_keywords = [
        "Apple Store", "apple store",
        "삼성", "Samsung", "samsung",
        "LG", "lg",
        "Coupang", "쿠팡",
        "SSG", "신세계",
        "롯데", "Lotte",
        "이마트", "E-MART", "e-mart",
        "홈플러스", "Homeplus",
        "NC백화점", "NC Department",
        "현대백화점",
        "전자랜드",
        "하이마트", "Hi-mart",
        "다이소", "Daiso",
        "올리브영", "Olive Young",
        "네이버", "Naver",
        "카카오", "Kakao",
        "11번가", "11st",
        "G마켓", "Gmarket",
        "옥션", "Auction",
        "인터파크", "Interpark",
        "위메프", "Wemakeprice",
        "티몬", "TMON",
    ]

    full_text = " ".join(lines)

    # 키워드 매칭
    for keyword in store_keywords:
        if keyword.lower() in full_text.lower():
            # 매칭된 키워드가 포함된 라인 전체를 반환
            for line in lines:
                if keyword.lower() in line.lower():
                    return line.strip()

    # 키워드 매칭이 안 되면 첫 번째 라인을 상호명으로 간주
    if lines:
        first_line = lines[0].strip()
        # 너무 짧거나 숫자만 있는 경우 스킵
        if len(first_line) > 1 and not first_line.replace("-", "").replace("/", "").isdigit():
            return first_line

    return None
