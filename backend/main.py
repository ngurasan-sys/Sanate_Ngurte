from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from broker_adapter import generate_historical_data, tick_stream

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/v1/chart/history")
async def get_chart_history(
    symbol: str = Query("NIFTY"),
    timeframe: str = Query("1m"),
    from_date: str = Query(None),
    to_date: str = Query(None)
):
    data = generate_historical_data(symbol, timeframe, from_date, to_date)
    return data

@app.websocket("/api/v1/chart/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await tick_stream.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        tick_stream.disconnect(websocket)
