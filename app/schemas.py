from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime

class PersonalDetails(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    age: int = Field(..., ge=13, le=100)
    gender: str = Field(..., pattern="^(male|female|other)$")
    height: float = Field(..., ge=100, le=250)  # cm
    weight: float = Field(..., ge=30, le=300)  # kg

class GoalPlanning(BaseModel):
    goal: str = Field(..., pattern="^(fat_loss|muscle_gain|maintenance)$")
    target_weight: Optional[float] = Field(None, ge=30, le=300)

class HealthConstraints(BaseModel):
    medical_conditions: Optional[str] = Field(None, max_length=500)
    food_allergies: Optional[str] = Field(None, max_length=500)
    diet_type: str = Field(..., pattern="^(veg|non_veg|vegan|vegetarian|pescatarian)$")
    disliked_foods: Optional[str] = Field(None, max_length=500)

class EatingHabits(BaseModel):
    meals_per_day: int = Field(..., ge=2, le=6)
    cooking_habits: str = Field(..., pattern="^(home_cooked|mixed|outside_food)$")

class Lifestyle(BaseModel):
    wake_time: str = Field(..., pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")
    sleep_time: str = Field(..., pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")
    work_hours: str = Field(..., max_length=50)
    activity_level: str = Field(..., pattern="^(sedentary|moderate|active)$")

class WorkoutInfo(BaseModel):
    workout_experience: str = Field(..., pattern="^(beginner|intermediate|advanced)$")
    workout_days_per_week: int = Field(..., ge=1, le=7)
    workout_duration: int = Field(..., ge=15, le=180)  # minutes

class UserInput(BaseModel):
    personal_details: PersonalDetails
    goal_planning: GoalPlanning
    health_constraints: HealthConstraints
    eating_habits: EatingHabits
    lifestyle: Lifestyle
    workout_info: WorkoutInfo
    
    @validator('goal_planning')
    def validate_target_weight(cls, v, values):
        if v.goal != 'maintenance' and not v.target_weight:
            raise ValueError('Target weight is required for fat_loss and muscle_gain goals')
        return v

class FollowUpQuestion(BaseModel):
    user_id: int
    plan_id: int
    question: str = Field(..., min_length=1, max_length=1000)

class PlanResponse(BaseModel):
    user_id: int
    plan_id: int
    diet_plan: Dict[str, Any]
    workout_plan: Dict[str, Any]
    explanation: str
    created_at: datetime

class ChatMessage(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=1000)

class ChatResponse(BaseModel):
    response: str
    current_step: str
    collected_data: Dict[str, Any]
    is_complete: bool = False
    plan_generated: bool = False
    user_id: Optional[int] = None
    plan_id: Optional[int] = None
    diet_plan: Optional[Dict[str, Any]] = None
    workout_plan: Optional[Dict[str, Any]] = None

