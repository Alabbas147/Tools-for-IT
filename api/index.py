from fastapi import FastAPI

app = FastAPI(title="WordPress Tools API")


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI"}
