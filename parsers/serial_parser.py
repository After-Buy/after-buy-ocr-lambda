import re
import logging

logger = logging.getLogger(__name__)

# 시리얼 넘버 근처에 나타나는 키워드
SERIAL_KEYWORDS = [
    re.compile(r"(?:Serial|SERIAL|serial|S\s*/\s*N|시리얼|일련번호|Serial\s*No\.?)[:\s]*(.+)", re.IGNORECASE),
]

# 시리얼 넘버 패턴 (영숫자 조합, 보통 8~20자)
SERIAL_PATTERNS = [
    # Apple 시리얼: C8QKL1234AB (10자리) 또는 12자리
    re.compile(r"\b([A-Z0-9]{10,12})\b"),
    # 범용 시리얼: 하이픈 포함 가능 (예: ABC-123-456)
    re.compile(r"\b([A-Z0-9](?:[A-Z0-9\-]){6,19}[A-Z0-9])\b"),
    # 숫자 위주 시리얼
    re.compile(r"\b(\d{8,20})\b"),
]

# 불용어 — 시리얼로 오인될 수 있는 패턴
SERIAL_EXCLUDE = {
    # 날짜 형태
    re.compile(r"^\d{4}$"),  # 연도
    re.compile(r"^\d{8}$"),  # YYYYMMDD일 가능성 높음
    # 전화번호
    re.compile(r"^\d{2,3}-\d{3,4}-\d{4}$"),
    # IP 주소
    re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"),
}


def parse_serial(lines: list[str]) -> dict | None:
    """
    기기 라벨 OCR 텍스트에서 시리얼 넘버를 추출.

    Args:
        lines: Textract에서 추출한 텍스트 라인 리스트

    Returns:
        {"serial_number": str} 또는 None
    """
    if not lines:
        return None

    # 1순위: 키워드 기반 추출 ("Serial: XXX" 형태)
    for line in lines:
        for keyword_pattern in SERIAL_KEYWORDS:
            match = keyword_pattern.search(line)
            if match:
                serial = match.group(1).strip()
                # 후처리: 공백 이후 텍스트 제거
                serial = serial.split()[0] if serial.split() else serial
                if _is_valid_serial(serial):
                    return {"serial_number": serial}

    # 2순위: 패턴 매칭으로 시리얼 후보 탐색
    candidates = []
    for line in lines:
        for pattern in SERIAL_PATTERNS:
            for match in pattern.finditer(line):
                candidate = match.group(1)
                if _is_valid_serial(candidate):
                    candidates.append(candidate)

    # 중복 제거 후 가장 많이 등장한 시리얼 선택
    if candidates:
        unique_candidates = list(dict.fromkeys(candidates))
        # 영문이 포함된 것 우선 (숫자만 있는 것보다 구체적)
        alpha_first = sorted(unique_candidates, key=lambda x: any(c.isalpha() for c in x), reverse=True)
        return {"serial_number": alpha_first[0]}

    logger.warning("시리얼 넘버를 추출하지 못함")
    return None


def _is_valid_serial(text: str) -> bool:
    """시리얼 넘버 후보가 유효한지 검증."""
    text = text.strip().upper()

    # 길이 검증
    # 하이픈 제거 후 6~20자리 영숫자
    clean = text.replace("-", "")
    if len(clean) < 6 or len(clean) > 20:
        return False

    # 영숫자와 하이픈만 허용
    if not re.match(r"^[A-Z0-9\-]+$", text):
        return False

    # 불용어 패턴 제외
    for exclude_pattern in SERIAL_EXCLUDE:
        if exclude_pattern.match(text):
            return False

    return True
