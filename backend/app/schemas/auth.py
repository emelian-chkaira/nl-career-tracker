import uuid
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field("", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str | None = None          # web uses the httpOnly cookie; mobile sends it in the body


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    name: str
    role: str
    profile: dict
    email_verified: bool = False


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class ProfileIn(BaseModel):
    skills: list[str] = []
    titles: list[str] = []
    cities: list[str] = []
    job_types: list[str] = []
    english_only: bool = False
    salary_category: str = "hsm_under30"


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ResetIn(TokenIn):
    new_password: str = Field(min_length=8, max_length=128)


class GoogleIn(BaseModel):
    credential: str = Field(min_length=20, max_length=4000)
