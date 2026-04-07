# After Buy - OCR Lambda

AWS Lambda + Amazon Textract 기반 OCR 처리 함수.

Lambda Function URL을 통해 Device Service(8082)에서 HTTP POST로 Base64 이미지를 받아 Textract로 텍스트를 추출하고, OCR 타입에 따라 파싱 결과를 반환합니다.

## 지원 OCR 타입

| 타입 | 설명 | 추출 항목 |
|---|---|---|
| `MODEL` | 기기 라벨 | 모델명 |
| `SERIAL` | 기기 라벨 | 시리얼 넘버 |
| `RECEIPT` | 구매 영수증 | 구매일, 구매가격, 구매처 |

## 프로젝트 구조

```
├── lambda_function.py       # Lambda 핸들러 (Function URL HTTP 이벤트 처리)
├── parsers/
│   ├── __init__.py
│   ├── receipt_parser.py    # 영수증 파서
│   ├── model_parser.py      # 모델명 파서
│   └── serial_parser.py     # 시리얼 넘버 파서
├── requirements.txt
├── .github/workflows/
│   └── deploy.yml           # GitHub Actions CI/CD
└── .gitignore
```

## 통신 방식

**Lambda Function URL**을 사용합니다. Device Service는 WebClient로 일반 HTTP POST를 보냅니다.

```
Device Service ──(HTTP POST)──→ Lambda Function URL ──→ Textract
                  Header: x-internal-secret-key: {내부 통신 키}
```

## 입력 / 출력

### 요청 (Device Service → Lambda Function URL)

```
POST https://xxxxxx.lambda-url.ap-northeast-2.on.aws/
Headers:
  Content-Type: application/json
  x-internal-secret-key: {INTERNAL_SECRET_KEY}

Body:
{
  "ocr_type": "RECEIPT",
  "image_base64": "/9j/4AAQSkZJRgABAQAAAQAB..."
}
```

### 응답 (Lambda → Device Service)

성공 (200):

```json
{
  "ocr_type": "RECEIPT",
  "is_success": true,
  "result": {
    "purchase_date": "2024-09-20",
    "purchase_price": 1550000,
    "purchase_store": "Apple Store 가로수길"
  }
}
```

실패 (200):

```json
{
  "ocr_type": "MODEL",
  "is_success": false,
  "result": null,
  "message": "텍스트를 인식하지 못했습니다. 다시 시도해주세요."
}
```

## 환경변수

| 변수 | 설명 |
|---|---|
| `INTERNAL_SECRET_KEY` | 내부 통신 인증용 시크릿 키 |

## 필요 GitHub Secrets

Lambda 배포 전용 IAM 사용자(`after-buy-lambda-deploy`)의 키를 사용합니다.
기존 백엔드 서비스의 AWS 키와 분리되어 있습니다.

| Secret | 설명 |
|---|---|
| `LAMBDA_DEPLOY_AWS_ACCESS_KEY_ID` | Lambda 배포 전용 IAM 액세스 키 |
| `LAMBDA_DEPLOY_AWS_SECRET_ACCESS_KEY` | Lambda 배포 전용 IAM 시크릿 키 |
| `AWS_REGION` | AWS 리전 (예: ap-northeast-2) |
| `LAMBDA_FUNCTION_NAME` | Lambda 함수명 (예: after-buy-ocr) |
