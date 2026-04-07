import base64
import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from parsers.receipt_parser import parse_receipt
from parsers.model_parser import parse_model
from parsers.serial_parser import parse_serial

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract = boto3.client("textract")

VALID_OCR_TYPES = {"MODEL", "SERIAL", "RECEIPT"}

INTERNAL_SECRET_KEY = os.environ.get("INTERNAL_SECRET_KEY", "")


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

    # 7. OCR 타입별 파싱
    try:
        if ocr_type == "RECEIPT":
            result = parse_receipt(lines)
        elif ocr_type == "MODEL":
            result = parse_model(lines)
        elif ocr_type == "SERIAL":
            result = parse_serial(lines)
    except Exception as e:
        logger.error("파싱 실패: %s", e)
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
