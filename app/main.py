from fastapi import FastAPI
from app.config import settings

from app.api.routes.users import router as users_router
from app.api.routes.teachers import router as teachers_router
from app.api.routes.students import router as students_router
from app.api.routes.schedules import router as schedules_router
from app.api.routes.lessons import router as lessons_router
from app.api.routes.transcripts import router as transcripts_router
from app.api.routes.analysis import router as analysis_router

app = FastAPI(title="AI English Tutor")

app.include_router(users_router)
app.include_router(teachers_router)
app.include_router(students_router)
app.include_router(schedules_router)
app.include_router(lessons_router)
app.include_router(transcripts_router)
app.include_router(analysis_router)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "database": settings.POSTGRES_DB,
    }