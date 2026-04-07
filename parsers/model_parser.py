import re
import logging

logger = logging.getLogger(__name__)

# 모델명 근처에 나타나는 키워드
MODEL_KEYWORDS = [
    re.compile(r"(?:Model|MODEL|model|모델명?|Model\s*Name)[:\s]*(.+)", re.IGNORECASE),
]

# 모델명 패턴 (영문+숫자+특수문자 조합, 보통 5~30자)
MODEL_PATTERNS = [
    # Apple 스타일: MTQN3KH/A, MJVY3KH/A
    re.compile(r"\b([A-Z]{2,5}\d{1,5}[A-Z]*/[A-Z])\b"),
    # Samsung 스타일: SM-G998N, SM-T870
    re.compile(r"\b(SM-[A-Z]?\d{3,5}[A-Z]?)\b"),
    # LG 스타일: LM-V600N
    re.compile(r"\b(LM-[A-Z]?\d{3,5}[A-Z]?)\b"),
    # 범용 영숫자 모델명 (4~30자, 영문+숫자 필수, 하이픈/슬래시 허용)
    re.compile(r"\b([A-Z0-9][A-Z0-9\-/]{3,29}[A-Z0-9])\b"),
]

# 불용어 — 모델명으로 오인될 수 있는 일반 단어들
MODEL_EXCLUDE = {
    "HTTP", "HTTPS", "HTML", "JSON", "WIFI", "BLUETOOTH",
    "MADE", "KOREA", "CHINA", "VIETNAM", "IMPORT",
    "SAFETY", "WARNING", "CAUTION", "NOTICE",
}


def parse_model(lines: list[str]) -> dict | None:
    """
    기기 라벨 OCR 텍스트에서 모델명을 추출.

    Args:
        lines: Textract에서 추출한 텍스트 라인 리스트

    Returns:
        {"model_name": str} 또는 None
    """
    if not lines:
        return None

    # 1순위: 키워드 기반 추출 ("Model: XXX" 형태)
    for line in lines:
        for keyword_pattern in MODEL_KEYWORDS:
            match = keyword_pattern.search(line)
            if match:
                model_name = match.group(1).strip()
                if _is_valid_model(model_name):
                    return {"model_name": model_name}

    # 2순위: 패턴 매칭으로 모델명 후보 탐색
    candidates = []
    for line in lines:
        for pattern in MODEL_PATTERNS:
            for match in pattern.finditer(line):
                candidate = match.group(1)
                if _is_valid_model(candidate):
                    candidates.append(candidate)

    # 중복 제거 후 가장 많이 등장한 모델명 선택
    if candidates:
        # 길이가 긴 순으로 정렬 (구체적인 모델명 우선)
        unique_candidates = list(dict.fromkeys(candidates))
        unique_candidates.sort(key=len, reverse=True)
        return {"model_name": unique_candidates[0]}

    logger.warning("모델명을 추출하지 못함")
    return None


def _is_valid_model(text: str) -> bool:
    """모델명 후보가 유효한지 검증."""
    text = text.strip().upper()

    # 너무 짧거나 긴 것 제외
    if len(text) < 3 or len(text) > 40:
        return False

    # 불용어 제외
    if text in MODEL_EXCLUDE:
        return False

    # 영문과 숫자가 모두 포함되어야 함 (진짜 모델명)
    has_alpha = any(c.isalpha() for c in text)
    has_digit = any(c.isdigit() for c in text)

    return has_alpha and has_digit
