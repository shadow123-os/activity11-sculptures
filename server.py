import logging
import os
from pathlib import Path as FilePath

from bson import ObjectId
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

load_dotenv(FilePath(__file__).with_name(".env"))
client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5000)
db = client["cs3720db"]
collection = db["sculptures"]
logger = logging.getLogger(__name__)

app = FastAPI(title="Activity 11 Sculptures API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class Sculpture(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    description: str = Field(min_length=1)
    imageUrl: HttpUrl
    alt: str = Field(min_length=1)


def check_collection():
    if "sculptures" not in db.list_collection_names(filter={"name": "sculptures"}):
        raise HTTPException(404, "Collection 'sculptures' not found. Import the seed data first.")


@app.exception_handler(DuplicateKeyError)
async def duplicate_name(_request: Request, _error: DuplicateKeyError):
    return JSONResponse(status_code=409, content={"detail": "A sculpture already has that name."})


@app.exception_handler(PyMongoError)
async def database_error(_request: Request, error: PyMongoError):
    logger.warning("Sculptures database operation failed (%s)", type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database operation failed. Try again."})


@app.get("/sculptures")
def get_sculptures():
    check_collection()
    return [{**record, "_id": str(record["_id"])} for record in collection.find()]


@app.post("/sculptures", status_code=201)
def add_sculpture(sculpture: Sculpture):
    check_collection()
    # The unique index protects the name check when requests overlap.
    collection.create_index("name", unique=True)
    result = collection.insert_one(sculpture.model_dump(mode="json"))
    return {"message": "Sculpture added successfully.", "_id": str(result.inserted_id)}


@app.put("/sculptures/{name:path}")
def update_sculpture(sculpture: Sculpture, name: str = Path(min_length=1)):
    if not name.strip():
        raise HTTPException(422, "Current sculpture name cannot be blank.")
    check_collection()
    collection.create_index("name", unique=True)
    record = collection.find_one_and_update(
        {"name": name.strip()},
        {"$set": sculpture.model_dump(mode="json")},
        return_document=ReturnDocument.AFTER,
    )
    if record is None:
        raise HTTPException(404, "Sculpture not found. Look up its current name.")
    return {"message": "Sculpture saved successfully.", "_id": str(record["_id"])}


@app.delete("/sculptures/{sculpture_id}")
def delete_sculpture(sculpture_id: str = Path(pattern=r"^[0-9a-fA-F]{24}$")):
    check_collection()
    record = collection.find_one_and_delete({"_id": ObjectId(sculpture_id)})
    if record is None:
        raise HTTPException(404, "Sculpture not found. It may have already been deleted.")
    return {"message": f"Sculpture '{record['name']}' deleted successfully.", "_id": str(record["_id"])}
