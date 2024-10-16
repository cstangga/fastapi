from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from models import ChatRequest, ChatResponse, FeedPost, PersonaChatRequest, TaskRequest
from services import (
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
from typing import List
from datetime import datetime
from firebase_admin import auth
from firebase_admin import firestore
from database import db
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
    print("모든 사용자의 새로운 일정을 생성하고 등록합니다...")
    users_ref = db.collection('users')
    users = users_ref.stream()
    
    for user in users:
        uid = user.id
        all_schedules = generate_and_save_user_schedule(uid)
        schedule_tasks(uid, all_schedules)  # uid 추가

# 라우트 정의

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest):
    return await chat_with_persona(chat_request)

@app.get("/personas")
async def get_personas_endpoint():
    return get_personas()

@app.post("/feed")
async def create_feed_post_endpoint(post: FeedPost):
    return await create_feed_post(post)

@app.post("/persona-chat")
async def persona_chat_endpoint(chat_request: PersonaChatRequest):
    return await persona_chat(chat_request)

@app.post("/execute-task")
async def execute_task_endpoint(task_request: TaskRequest, background_tasks: BackgroundTasks):
    task = create_task(task_request.uid, task_request.persona_name, task_request.target_name, task_request.topic)  # uid 추가
    background_tasks.add_task(task)
    return {"message": f"Task for {task_request.persona_name} interacting with {task_request.target_name} about {task_request.topic} has been scheduled."}

@app.post("/generate-user-schedule/{uid}")
async def generate_user_schedule_endpoint(uid: str, background_tasks: BackgroundTasks):
    all_schedules = generate_and_save_user_schedule(uid)
    background_tasks.add_task(schedule_tasks, uid, all_schedules)  # uid 추가
    return {"message": f"Schedule generated and saved for user {uid}"}

@app.get("/user-schedule/{uid}")
async def get_user_schedule_endpoint(uid: str):
    schedule = get_user_schedule(uid)
    if schedule:
        return schedule
    raise HTTPException(status_code=404, detail="Schedule not found for this user")

if __name__ == "__main__":
    import uvicorn
    print("FastAPI 서버 실행")
    uvicorn.run(app, host="0.0.0.0", port=8000)
