
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from models import ChatRequest, ChatResponse, FeedPost, PersonaChatRequest, TaskRequest
from service.services import send_expo_push_notification
import requests
from service.services import (
    chat_with_persona,
    get_personas,
    create_feed_post,
    persona_chat,
    generate_daily_schedule,
    schedule_tasks,
    create_task,
    generate_and_save_user_schedule,
    get_user_schedule,
)

from generate_image import (
    generate_persona_image,
    regenerate_image,
)

from typing import List
from datetime import datetime
from firebase_admin import auth
from firebase_admin import firestore
from database import db
# from villageServices import get_all_agents
from fastapi import WebSocket
# from villageServices import (
#     get_all_agents,
#     AgentManager  # 에이전트 관리를 위한 클래스
# )
import asyncio
# from service.personaChatVer2 import persona_chat_v2
from service.personaChatVer3 import simulate_conversation
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 실행
    scheduler.add_job(update_daily_schedule, CronTrigger(hour=1, minute=0)) # 매일 새벽 1시에 스케쥴 초기화
    scheduler.start()
    yield
    # 종료 시 실행
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)


async def update_daily_schedule():
    users_ref = db.collection('users')
    users = users_ref.stream()
    
    for user in users:
        uid = user.id
        all_schedules = generate_and_save_user_schedule(uid)
        await schedule_tasks_v2(uid, all_schedules)

async def schedule_tasks_v2(uid: str, all_schedules):
    for persona_schedule in all_schedules.schedules:
        for item in persona_schedule.schedule:
            chat_request = PersonaChatRequest(
                uid=uid,
                topic=item.topic,
                persona1=persona_schedule.persona,
                persona2=item.interaction_target,
                rounds=item.conversation_rounds
            )
            await simulate_conversation(chat_request)

# 라우트 정의
@app.post("/chat")
async def chat_endpoint(chat_request: ChatRequest):
    print("chat > chat_request : ", chat_request)
    uid = chat_request.user['uid']
    print("chat > uid : ", uid)
    
    response = await chat_with_persona(chat_request)
    print("chat > response : ", response)
    
    # 딕셔너리에서 값을 추출합니다.
    persona_name = response['persona_name']
    response_text = response['response']
    print("chat > persona_name : ", persona_name)
    print("chat > response_text : ", response_text)

    notification_result = send_expo_push_notification(uid, persona_name, response_text,"persona_chat")
    print("chat > notification_result : ", notification_result)
    # ChatResponse 모델에 맞게 반환
    return ChatResponse(persona_name=persona_name, response=response_text)
    # return await chat_with_persona(chat_request) 전에는 이거였음


@app.get("/personas")
async def get_personas_endpoint():
    return get_personas()

@app.post("/feed") # 피드 생성 엔드포인트
async def create_feed_post_endpoint(post: FeedPost):
    print("@app.post /feed 호출")
    return await create_feed_post(post)

@app.post("/persona-chat") # 페르소나 상호간의 대화 테스트 엔드포인트
async def persona_chat_endpoint(chat_request: PersonaChatRequest):
    return await persona_chat(chat_request)

@app.post("/v3/persona-chat") # 이게 최신버전임
async def persona_chat_v3_endpoint(chat_request: PersonaChatRequest):
    return await simulate_conversation(chat_request)

@app.post("/execute-task") # 페르소나 상호간의 대화 테스트 엔드포인트
async def execute_task_endpoint(task_request: TaskRequest, background_tasks: BackgroundTasks):
    task = create_task(
        task_request.uid,
        task_request.persona_name,
        task_request.interaction_target,
        task_request.topic,
        task_request.conversation_rounds
    )
    background_tasks.add_task(task)
    return {"message": f"Task for {task_request.persona_name} interacting with {task_request.interaction_target} about {task_request.topic} at {task_request.time} has been scheduled."}

@app.post("/generate-user-schedule/{uid}")
async def generate_user_schedule_endpoint(uid: str, background_tasks: BackgroundTasks):
    all_schedules = generate_and_save_user_schedule(uid)
    background_tasks.add_task(schedule_tasks, uid, all_schedules)
    return {"message": f"Schedule generated and saved for user {uid}"}

@app.get("/user-schedule/{uid}")
async def get_user_schedule_endpoint(uid: str):
    schedule = get_user_schedule(uid)
    if schedule:
        return schedule
    raise HTTPException(status_code=404, detail="Schedule not found for this user")

# @app.get("/api/agents/{uid}")
# async def read_agents(uid: str):
#     try:
#         agents = get_all_agents(uid)
#         return agents
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
    
# WebSocket 엔드포인트
# agent_manager = AgentManager()

# @app.websocket("/ws/{uid}")
# async def websocket_endpoint(websocket: WebSocket, uid: str):
#     await agent_manager.connect(websocket)
#     try:
#         while True:
#             # 에이전트 상태 업데이트
#             agent_manager.apply_schedule_to_agents(uid)
#             agent_manager.update_agents()
#             # 에이전트 위치 정보를 전송
#             positions = agent_manager.get_agents_positions()
#             await agent_manager.broadcast(str(positions))
#             await asyncio.sleep(1)  # 1초마다 업데이트
#     except WebSocketDisconnect:
#         agent_manager.disconnect(websocket)

@app.post("/generate-persona-image/{uid}")
async def generate_persona_image_endpoint(uid: str, image : UploadFile=File(...)):
    return await generate_persona_image(uid,image)

@app.post("/regenerate-image/{emotion}")
async def regenerate_image_endpoint(emotion: str, image : UploadFile=File(...)):
    return await regenerate_image(emotion, image)


@app.get("/networkcheck")
async def network_check_endpoint():
    print("network_check_endpoint 호출")
    return {"message": "Network check successful"}

@app.websocket("/ws")
async def websocket_endpoint(websocket : WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        print("data : ", data)
        await websocket.send_text(f"Message received: {data}")


if __name__ == "__main__":
    import uvicorn
    print("FastAPI 서버 실행")
    uvicorn.run(app, host="0.0.0.0", port=8000)
