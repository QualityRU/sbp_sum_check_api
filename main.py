from fastapi import FastAPI, HTTPException
from starlette.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import LOGIN, PASSWORD
from yoo import YooMoneyQRClient

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

client = YooMoneyQRClient(LOGIN, PASSWORD)


class QRDataRequest(BaseModel):
    data: str = Field(
        ...,
        example='https://qr.nspk.ru/AD20003FNSGB5S1G8IJPACMUOLTR9SOJ?type=02&bank=100000000001&sum=10700&cur=RUB&crc=B770',
    )


class OTPCode(BaseModel):
    code: str = Field(..., example='1234')


@app.post('/send_qr_payment')
async def send_qr_payment(request: QRDataRequest):
    try:
        if not request.data:
            raise HTTPException(status_code=400, detail='QR data is required')

        result = await client.process_qr(request.data)
        return JSONResponse(status_code=200, content={'success': result})

    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@app.post('/provide_otp')
async def provide_otp(request: OTPCode):
    try:
        await client.provide_otp(request.code)
        return {'message': '2FA код принят. Продолжаем авторизацию...'}
    except Exception as e:
        raise HTTPException(status_code=400, content={'error': str(e)})


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
