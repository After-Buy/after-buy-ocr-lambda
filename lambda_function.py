import base64
import json
import logging
import os
import re

import boto3
from botocore.exceptions import ClientError

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from parsers.receipt_parser import parse_receipt
from parsers.model_parser import parse_model
from parsers.serial_parser import parse_serial

# 로컬 개발 시 .env 파일에서 환경변수 로드
from pathlib import Path
_dotenv = Path(__file__).parent / ".env"
if _dotenv.exists():
    for line in _dotenv.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract = boto3.client("textract")

VALID_OCR_TYPES = {"MODEL", "SERIAL", "RECEIPT"}

INTERNAL_SECRET_KEY = os.environ.get("INTERNAL_SECRET_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

GEMINI_MODEL = "gemini-2.5-flash-lite"

SYSTEM_INSTRUCTION = (
    "당신은 OCR 텍스트 정제 어시스턴트입니다. "
    "Amazon Textract가 추출한 텍스트에서 구조화된 데이터를 JSON으로 추출합니다.\n"
    "규칙:\n"
    "- 텍스트에 확실히 존재하는 정보만 추출하세요.\n"
    "- 인식 불가능한 필드는 null로 반환하세요.\n"
    "- 날짜는 반드시 YYYY-MM-DD 형식의 문자열이어야 합니다.\n"
    "- 가격은 쉼표나 통화 기호 없는 정수(Number type)여야 합니다.\n"
    "- 매장명은 실제 사업장 이름이어야 하며, 주소나 전화번호는 제외하세요.\n"
    "- 추측하거나 임의로 정보를 만들지 마세요."
)

PROMPT_BY_TYPE = {
    "MODEL": (
        "다음 OCR 텍스트에서 기기 모델명을 추출하세요.\n"
        "모델명은 보통 'Model', '모델', '모델명' 근처에 있는 영숫자 코드입니다.\n"
        "예: Apple 스타일 MTQN3KH/A, Samsung 스타일 SM-G998N, LG 스타일 LM-V600N\n\n"
        "텍스트:\n{text_lines}"
    ),
    "SERIAL": (
        "다음 OCR 텍스트에서 기기 시리얼 넘버를 추출하세요.\n"
        "시리얼 넘버는 보통 'Serial', 'S/N', '시리얼', '일련번호' 근처에 있는 8~20자리 영숫자입니다.\n\n"
        "텍스트:\n{text_lines}"
    ),
    "RECEIPT": (
        "다음 영수증 OCR 텍스트에서 구매 정보를 추출하세요.\n"
        "- purchase_date: 구매일자 (YYYY-MM-DD 형식). '2024년 9월 20일', '24/09/20', '2024.09.20' 등 어떤 형식이든 변환.\n"
        "- purchase_price: 결제 금액 (콤마, 통화기호 없는 정수). 보통 '합계', '총', 'TOTAL', '결제금액' 근처의 가장 큰 금액.\n"
        "  단, 배송비, 적립금, 포인트, 할인, 쿠폰, 부가세는 제외.\n"
        "- purchase_store: 구매 매장명 (예: 'Apple Store 강남', '삼성디지털프라자').\n\n"
        "텍스트:\n{text_lines}"
    ),
}

SCHEMA_BY_TYPE = {
    "MODEL": {
        "type": "OBJECT",
        "properties": {
            "model_name": {"type": "STRING", "description": "기기 모델명"},
        },
        "required": ["model_name"],
    },
    "SERIAL": {
        "type": "OBJECT",
        "properties": {
            "serial_number": {"type": "STRING", "description": "기기 시리얼 넘버"},
        },
        "required": ["serial_number"],
    },
    "RECEIPT": {
        "type": "OBJECT",
        "properties": {
            "purchase_date": {"type": "STRING", "description": "구매일자 (YYYY-MM-DD)"},
            "purchase_price": {"type": "INTEGER", "description": "결제 금액 (정수)"},
            "purchase_store": {"type": "STRING", "description": "구매 매장명"},
        },
    },
}


def extract_with_gemini(ocr_type, lines):
    """Gemini API를 사용해 Textract 텍스트를 정제된 구조화 데이터로 변환."""
    if not GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY 미설정, Gemini 스킵")
        return None

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = PROMPT_BY_TYPE[ocr_type].format(text_lines=json.dumps(lines, ensure_ascii=False))
    schema = SCHEMA_BY_TYPE[ocr_type]

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=schema,
        ),
    )

    result = json.loads(response.text)
    logger.info("Gemini 응답: %s", result)

    validated = validate_gemini_result(ocr_type, result)
    return validated


def validate_gemini_result(ocr_type, result):
    """Gemini 응답이 백엔드 계약에 맞는지 검증. 실패 시 None 반환."""
    if not isinstance(result, dict):
        return None

    if ocr_type == "MODEL":
        model_name = result.get("model_name")
        if isinstance(model_name, str) and model_name.strip():
            return {"model_name": model_name.strip()}
        return None

    if ocr_type == "SERIAL":
        serial_number = result.get("serial_number")
        if isinstance(serial_number, str) and serial_number.strip():
            return {"serial_number": serial_number.strip()}
        return None

    if ocr_type == "RECEIPT":
        validated = {}
        has_any_field = False

        purchase_date = result.get("purchase_date")
        if isinstance(purchase_date, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", purchase_date):
            validated["purchase_date"] = purchase_date
            has_any_field = True

        purchase_price = result.get("purchase_price")
        if isinstance(purchase_price, (int, float)) and purchase_price > 0:
            validated["purchase_price"] = int(purchase_price)
            has_any_field = True

        purchase_store = result.get("purchase_store")
        if isinstance(purchase_store, str) and purchase_store.strip():
            validated["purchase_store"] = purchase_store.strip()
            has_any_field = True

        return validated if has_any_field else None

    return None


def lambda_handler(event, context):
    """
    Lambda Function URL을 통해 Device Service에서 HTTP POST로 요청 수신.

    Function URL 이벤트 형식:
        event = {
            "version": "2.0",
            "headers": {"x-internal-secret-key": "...", "content-type": "application/json", ...},
            "body": '{"ocr_type": "RECEIPT", "image_base64": "..."}',
            ...
        }
    """
    # 1. 내부 통신 인증
    headers = event.get("headers", {})
    request_key = headers.get("x-internal-secret-key", "")
    if INTERNAL_SECRET_KEY and request_key != INTERNAL_SECRET_KEY:
        logger.warning("인증 실패: 잘못된 INTERNAL_SECRET_KEY")
        return http_response(401, {"error": "인증에 실패했습니다."})

    # 2. 요청 본문 파싱
    body = event.get("body", "{}")
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return http_response(400, {"error": "잘못된 JSON 형식입니다."})

    logger.info("OCR 요청 수신: %s", {k: v for k, v in payload.items() if k != "image_base64"})

    # 3. 입력 검증
    ocr_type = payload.get("ocr_type", "").upper()
    image_base64 = payload.get("image_base64")

    if ocr_type not in VALID_OCR_TYPES:
        return http_response(400, error_body(ocr_type, f"유효하지 않은 ocr_type입니다. 지원: {VALID_OCR_TYPES}"))

    if not image_base64:
        return http_response(400, error_body(ocr_type, "image_base64가 누락되었습니다."))

    # 4. Base64 디코딩
    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception:
        return http_response(400, error_body(ocr_type, "image_base64 디코딩에 실패했습니다."))

    # 5. Textract 호출
    try:
        response = textract.detect_document_text(
            Document={"Bytes": image_bytes}
        )
    except ClientError as e:
        logger.error("Textract 호출 실패: %s", e)
        return http_response(500, error_body(ocr_type, "Textract 호출에 실패했습니다."))

    # 6. 텍스트 라인 추출
    lines = [block["Text"] for block in response.get("Blocks", []) if block["BlockType"] == "LINE"]

    if not lines:
        return http_response(200, error_body(ocr_type, "이미지에서 텍스트를 인식하지 못했습니다."))

    logger.info("추출된 텍스트 라인: %s", lines)

    # 7. Gemini 기반 파싱 (우선 시도)
    result = None
    try:
        result = extract_with_gemini(ocr_type, lines)
    except genai_errors.APIError as e:
        logger.warning("Gemini API 오류 (code=%s), regex 폴백: %s", e.code, e.message)
    except json.JSONDecodeError as e:
        logger.warning("Gemini 응답 JSON 파싱 실패, regex 폴백: %s", e)
    except Exception as e:
        logger.warning("Gemini 파싱 실패, regex 폴백: %s", e)

    # 8. Gemini 실패 시 regex 파서 폴백
    if result is None:
        logger.info("Regex 파서 폴백 실행")
        try:
            if ocr_type == "RECEIPT":
                result = parse_receipt(lines)
            elif ocr_type == "MODEL":
                result = parse_model(lines)
            elif ocr_type == "SERIAL":
                result = parse_serial(lines)
        except Exception as e:
            logger.error("Regex 파싱 실패: %s", e)
            return http_response(500, error_body(ocr_type, "텍스트 파싱에 실패했습니다."))

    if result is None:
        return http_response(200, error_body(ocr_type, "텍스트를 인식하지 못했습니다. 다시 시도해주세요."))

    return http_response(200, {
        "ocr_type": ocr_type,
        "is_success": True,
        "result": result,
    })


def http_response(status_code, body):
    """Lambda Function URL용 HTTP 응답 포맷."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def error_body(ocr_type, message):
    return {
        "ocr_type": ocr_type,
        "is_success": False,
        "result": None,
        "message": message,
    }
