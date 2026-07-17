import asyncio
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
import uvicorn

app = FastAPI()

@app.get("/stream")
async def stream():
    async def gen():
        yield "event: custom\ndata: {\"msg\": \"hello\"}\n\n"
        await asyncio.sleep(1)
        yield {"event": "custom2", "data": "{\"msg\": \"hello2\"}"}
    return EventSourceResponse(gen())

if __name__ == "__main__":
    uvicorn.run(app, port=8081)
