from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)
    height = Column(Float, nullable=False)  # in cm
    weight = Column(Float, nullable=False)  # in kg
    goal = Column(String, nullable=False)  # fat_loss, muscle_gain, maintenance
    target_weight = Column(Float, nullable=True)
    medical_conditions = Column(Text, nullable=True)
    food_allergies = Column(Text, nullable=True)
    diet_type = Column(String, nullable=False)  # veg, non_veg, vegan, etc.
    disliked_foods = Column(Text, nullable=True)
    meals_per_day = Column(Integer, nullable=False)
    cooking_habits = Column(String, nullable=False)  # home_cooked, mixed, outside_food
    wake_time = Column(String, nullable=False)  # HH:MM format
    sleep_time = Column(String, nullable=False)  # HH:MM format
    work_hours = Column(String, nullable=False)  # e.g., "9-17"
    activity_level = Column(String, nullable=False)  # sedentary, moderate, active
    workout_experience = Column(String, nullable=False)  # beginner, intermediate, advanced
    workout_days_per_week = Column(Integer, nullable=False)
    workout_duration = Column(Integer, nullable=False)  # in minutes
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class UserPlan(Base):
    __tablename__ = "user_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    diet_plan = Column(JSON, nullable=False)  # Weekly meal plan
    workout_plan = Column(JSON, nullable=False)  # Weekly workout plan
    explanation = Column(Text, nullable=True)  # AI-generated explanation
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)  # Can be null during data collection
    plan_id = Column(Integer, nullable=True, index=True)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    message_type = Column(String, nullable=True)  # 'user_input', 'system', 'followup'
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ConversationState(Base):
    __tablename__ = "conversation_states"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False, unique=True, index=True)  # Unique session identifier
    user_id = Column(Integer, nullable=True, index=True)
    plan_id = Column(Integer, nullable=True, index=True)  # Plan ID after generation
    current_step = Column(String, nullable=False, default='personal_details')  # Track which form step
    collected_data = Column(JSON, nullable=True)  # Store partially collected data
    is_complete = Column(Integer, default=0)  # 0 = collecting data, 1 = plan generated
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

