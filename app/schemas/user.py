from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    password: str


class UserOut(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
