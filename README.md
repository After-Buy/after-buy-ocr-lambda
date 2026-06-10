# After Buy OCR Lambda

AWS Lambda와 Amazon Textract를 활용한 After Buy OCR 처리 서비스입니다.

After Buy OCR Lambda는 Device Service로부터 제품 라벨 또는 영수증 이미지를 전달받아 텍스트를 추출하고, OCR 타입에 따라 필요한 정보를 파싱하여 반환합니다.

---

## Overview

전자제품을 등록할 때 사용자가 모델명, 시리얼 넘버, 구매일, 구매처, 구매가격을 직접 입력하는 것은 번거롭습니다.

이 서비스는 제품 라벨과 영수증 이미지에서 필요한 정보를 자동으로 추출하여 사용자 입력 과정을 줄이기 위해 만들어졌습니다.

Device Service는 이미지를 Base64 형식으로 Lambda Function URL에 전달하고, Lambda는 Amazon Textract를 통해 텍스트를 인식한 뒤 OCR 타입에 맞는 파서를 실행합니다.

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge\&logo=python\&logoColor=white)
![AWS Lambda](https://img.shields.io/badge/AWS_Lambda-FF9900?style=for-the-badge\&logo=awslambda\&logoColor=white)
![Amazon Textract](https://img.shields.io/badge/Amazon_Textract-FF9900?style=for-the-badge\&logo=amazonaws\&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge\&logo=githubactions\&logoColor=white)

---

## Features

### 제품 모델명 추출

제품 라벨 이미지에서 모델명을 추출합니다.

### 시리얼 넘버 추출

제품 라벨 이미지에서 시리얼 넘버를 추출합니다.

### 영수증 정보 추출

영수증 이미지에서 구매일, 구매가격, 구매처 정보를 추출합니다.

### 내부 통신 인증

Device Service와 Lambda 사이의 요청은 내부 시크릿 키를 통해 검증합니다.

---

## OCR Types

| OCR Type  | Description       | Result                                              |
| --------- | ----------------- | --------------------------------------------------- |
| `MODEL`   | 제품 라벨에서 모델명 추출    | `model_name`                                        |
| `SERIAL`  | 제품 라벨에서 시리얼 넘버 추출 | `serial_number`                                     |
| `RECEIPT` | 영수증에서 구매 정보 추출    | `purchase_date`, `purchase_price`, `purchase_store` |

---

## Architecture

<img width="1672" height="941" alt="image" src="https://github.com/user-attachments/assets/81e373a7-7a4c-4647-9db6-d7e3f95f07ad" />

---

## Request & Response

### Request

```http id="w0mkkz"
POST https://{lambda-function-url}
Content-Type: application/json
x-internal-secret-key: {INTERNAL_SECRET_KEY}
```

```json id="b0tsqi"
{
  "ocr_type": "RECEIPT",
  "image_base64": "/9j/4AAQSkZJRgABAQAAAQAB..."
}
```

---

### Success Response

```json id="f6f5fm"
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

---

### Failure Response

```json id="stfqsd"
{
  "ocr_type": "MODEL",
  "is_success": false,
  "result": null,
  "message": "텍스트를 인식하지 못했습니다. 다시 시도해주세요."
}
```

---

## Project Structure

```text id="8y4uw8"
after-buy-ocr-lambda
├── lambda_function.py
├── parsers
│   ├── __init__.py
│   ├── model_parser.py
│   ├── serial_parser.py
│   └── receipt_parser.py
├── requirements.txt
├── .env_example
├── .gitignore
└── .github
    └── workflows
        └── deploy.yml
```

---

## Main Files

| File                           | Description                               |
| ------------------------------ | ----------------------------------------- |
| `lambda_function.py`           | Lambda Function URL HTTP 이벤트를 처리하는 메인 핸들러 |
| `parsers/model_parser.py`      | 제품 모델명 파싱 로직                              |
| `parsers/serial_parser.py`     | 시리얼 넘버 파싱 로직                              |
| `parsers/receipt_parser.py`    | 영수증 구매 정보 파싱 로직                           |
| `requirements.txt`             | Lambda 실행에 필요한 Python 패키지 목록              |
| `.github/workflows/deploy.yml` | GitHub Actions 기반 Lambda 배포 워크플로우         |

---

## Environment Variables

| Variable              | Description                              |
| --------------------- | ---------------------------------------- |
| `INTERNAL_SECRET_KEY` | Device Service와 Lambda 간 내부 통신 인증용 시크릿 키 |

---

## GitHub Secrets

GitHub Actions를 통한 Lambda 배포를 위해 아래 Secrets가 필요합니다.

| Secret                                | Description                 |
| ------------------------------------- | --------------------------- |
| `LAMBDA_DEPLOY_AWS_ACCESS_KEY_ID`     | Lambda 배포 전용 IAM Access Key |
| `LAMBDA_DEPLOY_AWS_SECRET_ACCESS_KEY` | Lambda 배포 전용 IAM Secret Key |
| `AWS_REGION`                          | AWS 리전                      |
| `LAMBDA_FUNCTION_NAME`                | 배포 대상 Lambda 함수명            |

---

## Deployment Flow

```text id="qwc15o"
Push to develop branch
   ↓
GitHub Actions 실행
   ↓
Python dependencies 설치
   ↓
Lambda 배포 패키지 생성
   ↓
AWS Lambda 함수 업데이트
```

---

## Error Handling

| Case           | Description                            |
| -------------- | -------------------------------------- |
| 잘못된 내부 시크릿 키   | 요청을 거부합니다.                             |
| 지원하지 않는 OCR 타입 | 유효하지 않은 OCR 타입으로 처리합니다.                |
| 이미지 Base64 누락  | OCR 처리를 수행하지 않습니다.                     |
| Textract 인식 실패 | 사용자에게 재시도 메시지를 반환합니다.                  |
| 파싱 결과 없음       | `is_success: false`와 함께 실패 메시지를 반환합니다. |

---

## Related Repositories

| Repository                                                                        | Description                  |
| --------------------------------------------------------------------------------- | ---------------------------- |
| [after-buy-device-service](https://github.com/After-Buy/after-buy-device-service) | OCR Lambda를 호출하는 전자제품 관리 서비스 |
| [after-buy-infra](https://github.com/After-Buy/after-buy-infra)                   | After Buy 인프라 및 배포 설정        |
| [After-Buy Organization](https://github.com/After-Buy)                            | After Buy 전체 프로젝트            |

---

## Role in After Buy

이 Lambda는 After Buy 서비스에서 사용자의 입력 부담을 줄이는 역할을 담당합니다.

제품 라벨과 영수증 이미지를 분석하여 전자제품 등록 과정에서 필요한 정보를 자동으로 추출하고, Device Service가 해당 결과를 저장할 수 있도록 정제된 OCR 결과를 반환합니다.
