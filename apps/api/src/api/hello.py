from fastapi import APIRouter, Query

router = APIRouter()

@router.get("/hello")
async def hello(name: str = Query("world")):
    return {"greeting": f"Hello, {name}!"}
