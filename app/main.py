from fastapi import FastAPI

app = FastAPI(title="AI English Tutor")


@app.get("/health")
def health_check():
    return {"status": "ok"}