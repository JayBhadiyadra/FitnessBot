"""
FastAPI main application with endpoints for the fitness chatbot.
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import os

from app.database import get_db, engine, Base
from app.models import User, UserPlan, Conversation, ConversationState
from app.schemas import UserInput, FollowUpQuestion, PlanResponse, ChatMessage, ChatResponse
from app.core_logic import DietPlanGenerator, WorkoutPlanGenerator
from app.gemini_service import GeminiService
from app.conversation_flow import ConversationFlow
from app.conversation_summary import generate_conversation_summary, get_missing_fields
import json
import re

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fitness Plan Chatbot API",
    description="Personalized Diet & Workout Plan Chatbot",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Gemini service
try:
    # Reload environment variables to ensure latest API key is used
    from dotenv import load_dotenv
    load_dotenv()
    
    gemini_service = GeminiService()
    print("✓ Gemini service initialized successfully")
except Exception as e:
    print(f"⚠ Warning: Gemini service initialization failed: {e}")
    print("⚠ The application will work with fallback responses (no AI features)")
    print("⚠ To fix: Check your GEMINI_API_KEY in .env file and restart the application")
    gemini_service = None

# Serve static files (frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main HTML page."""
    try:
        return FileResponse("static/index.html")
    except:
        return HTMLResponse("""
        <html>
            <head><title>Fitness Chatbot</title></head>
            <body>
                <h1>Fitness Plan Chatbot API</h1>
                <p>API is running. Please ensure the frontend files are in the static/ directory.</p>
                <p><a href="/docs">API Documentation</a></p>
            </body>
        </html>
        """)

@app.post("/api/chat/start", status_code=status.HTTP_200_OK)
async def start_conversation(db: Session = Depends(get_db)):
    """Start a new conversation session."""
    session_id = ConversationFlow.generate_session_id()
    
    # Create conversation state
    state = ConversationState(
        session_id=session_id,
        current_step='personal_details',
        collected_data={},
        is_complete=0
    )
    db.add(state)
    db.commit()
    
    # Get initial greeting from AI
    initial_message = ""
    if gemini_service:
        try:
            initial_message = gemini_service.generate_conversational_response(
                'personal_details',
                "",
                {},
                None
            )
        except:
            initial_message = "👋 Hi! I'm your fitness coach. Let's create your personalized plan! What's your name?"
    else:
        initial_message = "👋 Hi! I'm your fitness coach. Let's create your personalized plan! What's your name?"
    
    # Save initial bot message
    conv = Conversation(
        user_id=None,
        plan_id=None,
        message="",
        response=initial_message,
        message_type='system'
    )
    db.add(conv)
    db.commit()
    
    return {
        "session_id": session_id,
        "response": initial_message,
        "current_step": "personal_details"
    }

def extract_field_value(field: str, message: str, message_lower: str) -> Optional[Any]:
    """Extract field value from user message using simple pattern matching."""
    # Number extraction - preserve negative signs
    if field in ['age', 'height', 'weight', 'target_weight', 'meals_per_day', 
                 'workout_days_per_week', 'workout_duration']:
        # Match numbers with optional negative sign and decimal
        number_pattern = r'-?\d+\.?\d*'
        numbers = re.findall(number_pattern, message)
        if numbers:
            num_str = numbers[0]
            # Validate it's actually a number (not just a dash)
            try:
                num_value = float(num_str)
                # Field-specific validation to prevent extracting wrong numbers
                if field == 'age' and (num_value < 13 or num_value > 100):
                    return None  # Age out of range, don't extract
                elif field == 'height' and (num_value < 100 or num_value > 250):
                    return None  # Height out of range, don't extract
                elif field == 'weight' and (num_value < 30 or num_value > 300):
                    return None  # Weight out of range, don't extract
                elif field == 'target_weight' and (num_value < 30 or num_value > 300):
                    return None  # Target weight out of range
                elif field == 'meals_per_day' and (num_value < 2 or num_value > 6):
                    return None  # Meals out of range
                elif field == 'workout_days_per_week' and (num_value < 1 or num_value > 7):
                    return None  # Days out of range
                elif field == 'workout_duration' and (num_value < 15 or num_value > 180):
                    return None  # Duration out of range
                # Return as string to preserve sign for validation
                return num_str
            except ValueError:
                return None
    
    # Name extraction
    if field == 'name':
        # Handle various name formats
        message_lower = message.lower().strip()
        
        # Reject common non-name responses
        reject_patterns = [
            'no', 'nothing', 'none', "don't", "dont", "don't want", "dont want",
            'skip', 'pass', 'not', "won't", "wont", 'refuse', 'decline',
            'n/a', 'na', 'nope', 'nah', 'no thanks', 'no thank you'
        ]
        
        # Check if message is a rejection
        for pattern in reject_patterns:
            if message_lower == pattern or message_lower.startswith(pattern + ' ') or message_lower.endswith(' ' + pattern):
                return None  # Reject as name
        
        # Remove common prefixes
        prefixes = ['my name is', "i'm", "i am", 'name is', 'call me', 'this is', 'it\'s', 'its', 'i am called']
        extracted_name = None
        
        for prefix in prefixes:
            if prefix in message_lower:
                # Extract name after prefix
                name_part = message[message_lower.find(prefix) + len(prefix):].strip()
                # Remove trailing punctuation and common words
                name_part = name_part.rstrip('.,!?')
                words = name_part.split()
                if words:
                    # Take first 1-3 words as name (handles first and last names)
                    extracted_name = ' '.join(words[:3]).strip()
                    break
        
        # If no prefix, take first meaningful words (skip common words)
        if not extracted_name:
            skip_words = ['hi', 'hello', 'hey', 'the', 'a', 'an', 'is', 'my', 'name', 'i', 'am']
            words = message.strip().split()
            meaningful_words = [w for w in words if w.lower() not in skip_words]
            
            if meaningful_words:
                # Take first 1-3 words as name
                extracted_name = ' '.join(meaningful_words[:3]).strip()
            elif words:
                # Fallback: take first 1-2 words
                extracted_name = ' '.join(words[:2]).strip()
        
        # Final validation: reject if it's still a rejection pattern or too short
        if extracted_name:
            extracted_lower = extracted_name.lower().strip()
            # Reject if it matches rejection patterns
            for pattern in reject_patterns:
                if extracted_lower == pattern:
                    return None
            # Reject if it's just numbers or special characters
            if extracted_name.isdigit() or len(extracted_name.strip()) < 2:
                return None
            # Reject if it contains only common words
            if extracted_lower in ['yes', 'ok', 'okay', 'sure', 'fine', 'alright']:
                return None
            return extracted_name
        
        return None
    
    # Gender extraction
    if field == 'gender':
        if any(word in message_lower for word in ['male', 'man', 'boy', 'guy']):
            return 'male'
        elif any(word in message_lower for word in ['female', 'woman', 'girl', 'lady']):
            return 'female'
        elif 'other' in message_lower:
            return 'other'
    
    # Goal extraction
    if field == 'goal':
        if any(word in message_lower for word in ['fat loss', 'lose weight', 'weight loss', 'slim', 'fat']):
            return 'fat_loss'
        elif any(word in message_lower for word in ['muscle', 'gain', 'bulk', 'build']):
            return 'muscle_gain'
        elif any(word in message_lower for word in ['maintain', 'maintenance', 'stay']):
            return 'maintenance'
    
    # Diet type extraction - improved to handle more variations
    if field == 'diet_type':
        message_lower = message.lower().strip()
        
        # Check for vegan first (most specific)
        if 'vegan' in message_lower:
            return 'vegan'
        # Check for pescatarian
        elif 'pescatarian' in message_lower or 'pesca' in message_lower:
            return 'pescatarian'
        # Check for vegetarian/veg
        elif any(word in message_lower for word in ['vegetarian', 'veg', 'veggie']):
            # Make sure it's not non-vegetarian
            if not any(word in message_lower for word in ['non', 'not', 'no']):
                return 'veg'
        # Check for non-vegetarian/non-veg
        if any(word in message_lower for word in ['non-veg', 'non veg', 'nonvegetarian', 'non vegetarian', 
                                                   'meat', 'chicken', 'beef', 'pork', 'nonveg']):
            return 'non_veg'
        # Also check if user says they eat meat
        if any(word in message_lower for word in ['eat meat', 'eats meat', 'meat eater', 'i eat meat']):
            return 'non_veg'
    
    # Activity level
    if field == 'activity_level':
        if 'sedentary' in message_lower or 'low' in message_lower:
            return 'sedentary'
        elif 'moderate' in message_lower or 'medium' in message_lower:
            return 'moderate'
        elif 'active' in message_lower or 'high' in message_lower:
            return 'active'
    
    # Workout experience
    if field == 'workout_experience':
        if 'beginner' in message_lower or 'new' in message_lower or 'start' in message_lower:
            return 'beginner'
        elif 'intermediate' in message_lower or 'some' in message_lower:
            return 'intermediate'
        elif 'advanced' in message_lower or 'expert' in message_lower or 'experienced' in message_lower:
            return 'advanced'
    
    # Cooking habits - check this BEFORE work_hours to avoid conflicts
    if field == 'cooking_habits':
        if 'home' in message_lower or 'cook' in message_lower:
            return 'home_cooked'
        elif 'outside' in message_lower or 'restaurant' in message_lower or 'eat out' in message_lower:
            return 'outside_food'
        elif 'mixed' in message_lower or 'mix' in message_lower or 'both' in message_lower:
            return 'mixed'
    
    # Time extraction
    if field in ['wake_time', 'sleep_time']:
        time_match = re.search(r'(\d{1,2}):(\d{2})', message)
        if time_match:
            return time_match.group(0)
        time_match = re.search(r'(\d{1,2})\s*(am|pm)', message_lower)
        if time_match:
            hour = int(time_match.group(1))
            am_pm = time_match.group(2)
            if am_pm == 'pm' and hour != 12:
                hour += 12
            elif am_pm == 'am' and hour == 12:
                hour = 0
            return f"{hour:02d}:00"
    
    # Text fields - but exclude diet-related words for medical_conditions and food_allergies
    if field == 'medical_conditions':
        # Don't extract diet-related words as medical conditions
        message_lower = message.lower()
        diet_words = ['veg', 'vegetarian', 'vegan', 'non-veg', 'non veg', 'pescatarian', 'meat', 'chicken', 'beef', 'pork']
        if any(word in message_lower for word in diet_words):
            return None  # This is likely a diet type, not a medical condition
        if len(message.strip()) > 2:
            return message.strip()
    
    if field == 'food_allergies':
        # Don't extract diet-related words as food allergies
        message_lower = message.lower()
        diet_words = ['veg', 'vegetarian', 'vegan', 'non-veg', 'non veg', 'pescatarian', 'meat', 'chicken', 'beef', 'pork']
        if any(word in message_lower for word in diet_words):
            return None  # This is likely a diet type, not a food allergy
        if len(message.strip()) > 2:
            return message.strip()
    
    # Work hours - only extract if it's NOT a cooking_habits response
    if field == 'work_hours':
        # Exclude cooking-related words to avoid conflicts
        cooking_words = ['mix', 'mixed', 'home', 'cook', 'outside', 'restaurant', 'both', 'prepared', 'pre-prepare']
        if any(word in message_lower for word in cooking_words):
            return None  # This is likely cooking_habits, not work_hours
        if len(message.strip()) > 2:  # Not just "yes", "no", etc.
            return message.strip()
    
    if field == 'disliked_foods':
        if len(message.strip()) > 2:  # Not just "yes", "no", etc.
            return message.strip()
    
    return None

def get_fallback_response(step: str, collected_data: Dict[str, Any], missing_fields: Optional[list] = None) -> str:
    """Get fallback response when AI is unavailable."""
    # Use missing fields to determine what to ask next
    if missing_fields and len(missing_fields) > 0:
        next_field = missing_fields[0]
        field_prompts = {
            'name': f"Great! Let's get started. What's your name?",
            'age': f"Nice to meet you, {collected_data.get('name', 'there')}! How old are you?",
            'gender': f"Thanks! What's your gender - male, female, or other?",
            'height': f"Perfect! What's your height in centimeters?",
            'weight': f"Great! What's your current weight in kilograms?",
            'goal': "What's your fitness goal - fat loss, muscle gain, or maintenance?",
            'target_weight': f"Excellent! What's your target weight in kilograms?",
            'diet_type': "What's your diet type - vegetarian, non-vegetarian, vegan, or pescatarian?",
            'food_allergies': "Do you have any food allergies?",
            'disliked_foods': "Are there any foods you dislike?",
            'meals_per_day': "How many meals do you typically eat per day?",
            'cooking_habits': "What are your cooking habits - home cooked, mixed, or outside food?",
            'wake_time': "What time do you usually wake up? (e.g., 07:00)",
            'sleep_time': "What time do you usually go to sleep? (e.g., 23:00)",
            'work_hours': "What are your work hours? (e.g., 9-17)",
            'activity_level': "What's your activity level - sedentary, moderate, or active?",
            'workout_experience': "What's your workout experience level - beginner, intermediate, or advanced?",
            'workout_days_per_week': "How many days per week can you work out?",
            'workout_duration': "How long can you work out per session in minutes?"
        }
        return field_prompts.get(next_field, f"Please provide your {next_field.replace('_', ' ')}.")
    
    # Fallback to step-based responses
    fallbacks = {
        'personal_details': "Great! What's your name?" if not collected_data.get('name') else "What's your age?",
        'goal_planning': "What's your fitness goal - fat loss, muscle gain, or maintenance?",
        'health_constraints': "Do you have any food allergies?",
        'eating_lifestyle': "How many meals do you eat per day?",
        'workout_info': "What's your workout experience level?"
    }
    return fallbacks.get(step, "Please continue...")

async def generate_plan_from_collected_data(
    state: ConversationState,
    collected_data: Dict[str, Any],
    db: Session
) -> ChatResponse:
    """Generate plan from collected data."""
    try:
        # Required fields for User model (nullable=False)
        required_fields = [
            'name', 'age', 'gender', 'height', 'weight', 'goal', 'diet_type',
            'meals_per_day', 'cooking_habits', 'wake_time', 'sleep_time',
            'work_hours', 'activity_level', 'workout_experience',
            'workout_days_per_week', 'workout_duration'
        ]
        
        # Check for missing required fields
        missing_required = [field for field in required_fields if not collected_data.get(field)]
        if missing_required:
            error_msg = f"Missing required fields: {', '.join(missing_required)}. Collected data: {collected_data}"
            print(f"ERROR: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required information: {', '.join(missing_required)}. Please provide all required details."
            )
        
        user_data = {
            'name': collected_data.get('name', 'User'),
            'age': collected_data.get('age'),
            'gender': collected_data.get('gender'),
            'height': collected_data.get('height'),
            'weight': collected_data.get('weight'),
            'goal': collected_data.get('goal'),
            'target_weight': collected_data.get('target_weight'),
            'medical_conditions': collected_data.get('medical_conditions'),
            'food_allergies': collected_data.get('food_allergies'),
            'diet_type': collected_data.get('diet_type'),
            'disliked_foods': collected_data.get('disliked_foods'),
            'meals_per_day': collected_data.get('meals_per_day'),
            'cooking_habits': collected_data.get('cooking_habits'),
            'wake_time': collected_data.get('wake_time'),
            'sleep_time': collected_data.get('sleep_time'),
            'work_hours': collected_data.get('work_hours'),
            'activity_level': collected_data.get('activity_level'),
            'workout_experience': collected_data.get('workout_experience'),
            'workout_days_per_week': collected_data.get('workout_days_per_week'),
            'workout_duration': collected_data.get('workout_duration')
        }
        
        print(f"DEBUG: Creating user with data: {user_data}")
        db_user = User(**user_data)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        diet_plan = DietPlanGenerator.generate_weekly_meal_plan(user_data)
        workout_plan = WorkoutPlanGenerator.generate_weekly_workout_plan(user_data)
        
        # Generate explanation using AI (LLM)
        explanation = ""
        if gemini_service:
            try:
                explanation = gemini_service.generate_plan_explanation(user_data, diet_plan, workout_plan)
                print("DEBUG: Generated explanation from Gemini AI (LLM)")
            except Exception as e:
                error_msg = str(e).lower()
                if '429' in error_msg or 'rate limit' in error_msg:
                    print(f"DEBUG: Gemini API rate limit (429) - using fallback explanation")
                else:
                    print(f"DEBUG: Error generating explanation from LLM: {e}")
                # The generate_plan_explanation method has its own fallback, so call it again
                # It will return the fallback message
                explanation = gemini_service.generate_plan_explanation(user_data, diet_plan, workout_plan)
        else:
            # Fallback when Gemini service is not available
            goal_text = user_data.get('goal', 'your fitness').replace('_', ' ')
            explanation = f"""Great news! I've created a personalized fitness plan tailored specifically for you.

Your daily nutrition targets {diet_plan.get('daily_targets', {}).get('calories')} calories, with a balanced macronutrient breakdown. Your workout plan includes {user_data.get('workout_days_per_week')} sessions per week, each lasting {user_data.get('workout_duration')} minutes, designed for your {user_data.get('workout_experience')} experience level.

This plan is customized for your {user_data.get('diet_type', 'preferred').replace('_', ' ')} diet preferences and is designed to help you achieve your {goal_text} goal. Feel free to ask me any questions about your plan!"""
        
        # Strip markdown from explanation
        import re
        explanation = re.sub(r'\*\*([^*]+)\*\*', r'\1', explanation)  # Remove **bold**
        explanation = re.sub(r'\*([^*]+)\*', r'\1', explanation)  # Remove *italic*
        explanation = explanation.strip()
        
        db_plan = UserPlan(
            user_id=db_user.id,
            diet_plan=diet_plan,
            workout_plan=workout_plan,
            explanation=explanation
        )
        db.add(db_plan)
        db.commit()
        db.refresh(db_plan)
        
        state.user_id = db_user.id
        state.plan_id = db_plan.id
        state.is_complete = 1
        db.commit()
        
        plan_message = f"{explanation}\n\nYour personalized diet and workout plan has been generated! You can ask me any questions about it."
        conv = Conversation(
            user_id=db_user.id,
            plan_id=db_plan.id,
            message="Generate plan",
            response=plan_message,
            message_type='system'
        )
        db.add(conv)
        db.commit()
        
        return ChatResponse(
            response=plan_message,
            current_step='complete',
            collected_data=collected_data,
            is_complete=True,
            plan_generated=True,
            user_id=db_user.id,
            plan_id=db_plan.id,
            diet_plan=diet_plan,
            workout_plan=workout_plan
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR in generate_plan_from_collected_data: {str(e)}")
        print(f"Traceback: {error_trace}")
        print(f"Collected data: {collected_data}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating plan: {str(e)}"
        )

@app.post("/api/chat/message", response_model=ChatResponse)
async def handle_chat_message(chat_msg: ChatMessage, db: Session = Depends(get_db)):
    """Handle a chat message in the conversational flow."""
    state = db.query(ConversationState).filter(
        ConversationState.session_id == chat_msg.session_id
    ).first()
    
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found. Please start a new conversation."
        )
    
    if state.is_complete == 1:
        # Plan already generated - handle as follow-up question
        return await handle_followup_question(chat_msg, state, db)
    
    # Get conversation history for this session
    history = db.query(Conversation).filter(
        Conversation.user_id == (state.user_id if state.user_id else None)
    ).order_by(Conversation.created_at.desc()).limit(10).all()
    
    history_list = [
        {"message": conv.message, "response": conv.response}
        for conv in reversed(history)
    ]
    
    collected_data = state.collected_data or {}
    current_step = state.current_step
    user_message_lower = chat_msg.message.lower()
    
    step_fields = ConversationFlow.STEP_FIELDS.get(current_step, [])
    field_collected = False  # Track if we collected a field in this message
    
    # Priority: If we're in eating_lifestyle and message contains cooking keywords, check cooking_habits first
    if current_step == 'eating_lifestyle' and 'cooking_habits' not in collected_data:
        cooking_keywords = ['mix', 'mixed', 'home', 'cook', 'outside', 'restaurant', 'both', 'prepared', 'pre-prepare', 'eat out']
        if any(keyword in user_message_lower for keyword in cooking_keywords):
            # Try to extract cooking_habits first (priority)
            value = extract_field_value('cooking_habits', chat_msg.message, user_message_lower)
            if value:
                is_valid, error_msg = ConversationFlow.validate_field('cooking_habits', value, current_step)
                if is_valid:
                    try:
                        collected_data['cooking_habits'] = str(value).strip()
                        state.collected_data = collected_data
                        db.commit()
                        print(f"DEBUG: Collected cooking_habits (priority) = {collected_data['cooking_habits']}")
                        field_collected = True
                    except Exception as e:
                        print(f"Error processing cooking_habits: {e}")
    
    # Priority: If we're in health_constraints and message contains diet keywords, check diet_type first
    if current_step == 'health_constraints' and 'diet_type' not in collected_data and not field_collected:
        diet_keywords = ['veg', 'vegetarian', 'vegan', 'non-veg', 'non veg', 'pescatarian', 'meat', 'chicken', 'beef', 'pork']
        if any(keyword in user_message_lower for keyword in diet_keywords):
            # Try to extract diet_type first (priority)
            value = extract_field_value('diet_type', chat_msg.message, user_message_lower)
            if value:
                is_valid, error_msg = ConversationFlow.validate_field('diet_type', value, current_step)
                if is_valid:
                    try:
                        value_lower = str(value).lower().strip()
                        if 'vegan' in value_lower:
                            collected_data['diet_type'] = 'vegan'
                        elif 'pescatarian' in value_lower or 'pesca' in value_lower:
                            collected_data['diet_type'] = 'pescatarian'
                        elif any(word in value_lower for word in ['non', 'meat', 'chicken']) or 'non-veg' in value_lower:
                            collected_data['diet_type'] = 'non_veg'
                        elif any(word in value_lower for word in ['veg', 'vegetarian']):
                            collected_data['diet_type'] = 'veg'
                        else:
                            collected_data['diet_type'] = str(value).strip()
                        state.collected_data = collected_data
                        db.commit()
                        print(f"DEBUG: Collected diet_type (priority) = {collected_data['diet_type']}")
                        field_collected = True
                    except Exception as e:
                        print(f"Error processing diet_type: {e}")
    
    # Only try to extract ONE field at a time - the first missing field
    # Skip the loop if we already collected cooking_habits or diet_type in priority check above
    if not field_collected:
        for field in step_fields:
            if field not in collected_data or not collected_data[field]:
                # Skip if we already processed it in priority check
                if (field == 'diet_type' or field == 'cooking_habits') and field_collected:
                    continue
                # Only extract if this is the first missing field to avoid extracting same value for multiple fields
                value = extract_field_value(field, chat_msg.message, user_message_lower)
                if value:
                    # Validate BEFORE converting to number
                    is_valid, error_msg = ConversationFlow.validate_field(field, value, current_step)
                    if is_valid:
                        # Only convert after validation passes
                        try:
                            if field in ['age', 'meals_per_day', 'workout_days_per_week', 'workout_duration']:
                                collected_data[field] = int(float(value))
                            elif field in ['height', 'weight', 'target_weight']:
                                collected_data[field] = float(value)
                            elif field == 'diet_type':
                                # Normalize diet_type values to standard format
                                value_lower = str(value).lower().strip()
                                if 'vegan' in value_lower:
                                    collected_data[field] = 'vegan'
                                elif 'pescatarian' in value_lower or 'pesca' in value_lower:
                                    collected_data[field] = 'pescatarian'
                                elif any(word in value_lower for word in ['non', 'meat', 'chicken']) or 'non-veg' in value_lower:
                                    collected_data[field] = 'non_veg'
                                elif any(word in value_lower for word in ['veg', 'vegetarian']):
                                    collected_data[field] = 'veg'
                                else:
                                    collected_data[field] = str(value).strip()
                            elif field == 'cooking_habits':
                                # Normalize cooking_habits - already normalized by extract_field_value, but ensure consistency
                                collected_data[field] = str(value).strip()
                            else:
                                collected_data[field] = str(value).strip()
                            field_collected = True
                            # Update state immediately after collecting
                            state.collected_data = collected_data
                            db.commit()
                            print(f"DEBUG: Collected {field} = {collected_data[field]}")  # Debug log
                            # Break after collecting one field to avoid extracting same value for multiple fields
                            break
                        except (ValueError, TypeError) as e:
                            # If conversion fails, return error
                            bot_response = f"Please enter a valid number for {field.replace('_', ' ')}."
                            conv = Conversation(
                                user_id=state.user_id,
                                plan_id=state.plan_id,
                                message=chat_msg.message,
                                response=bot_response,
                                message_type='user_input'
                            )
                            db.add(conv)
                            db.commit()
                            return ChatResponse(
                                response=bot_response,
                                current_step=current_step,
                                collected_data=collected_data,
                                is_complete=False
                            )
                    else:
                        bot_response = error_msg
                        conv = Conversation(
                            user_id=state.user_id,
                            plan_id=state.plan_id,
                            message=chat_msg.message,
                            response=bot_response,
                            message_type='user_input'
                        )
                        db.add(conv)
                        state.collected_data = collected_data
                        db.commit()
                        
                        return ChatResponse(
                            response=bot_response,
                            current_step=current_step,
                            collected_data=collected_data,
                            is_complete=False
                        )
    
    # Check if step is complete AFTER processing the message
    if ConversationFlow.is_step_complete(collected_data, current_step):
        next_step = ConversationFlow.get_next_step(current_step)
        if next_step:
            current_step = next_step
            # Update state with new step
            state.current_step = current_step
            state.collected_data = collected_data
            db.commit()
            print(f"DEBUG: Step complete, moving to {current_step}")
        else:
            # All steps complete - validate all required fields before generating plan
            print(f"DEBUG: All steps complete. Collected data before plan generation: {collected_data}")
            required_fields = [
                'name', 'age', 'gender', 'height', 'weight', 'goal', 'diet_type',
                'meals_per_day', 'cooking_habits', 'wake_time', 'sleep_time',
                'work_hours', 'activity_level', 'workout_experience',
                'workout_days_per_week', 'workout_duration'
            ]
            missing_fields = [f for f in required_fields if not collected_data.get(f)]
            if missing_fields:
                print(f"ERROR: Missing required fields: {missing_fields}")
                bot_response = f"I need a bit more information. Please provide: {', '.join(missing_fields)}."
                conv = Conversation(
                    user_id=state.user_id,
                    plan_id=state.plan_id,
                    message=chat_msg.message,
                    response=bot_response,
                    message_type='user_input'
                )
                db.add(conv)
                state.collected_data = collected_data
                db.commit()
                return ChatResponse(
                    response=bot_response,
                    current_step=current_step,
                    collected_data=collected_data,
                    is_complete=False
                )
            return await generate_plan_from_collected_data(state, collected_data, db)
    
    # Generate conversation summary for better context
    conversation_summary = generate_conversation_summary(collected_data, current_step)
    missing_fields = get_missing_fields(collected_data, current_step)
    
    # Debug: Print what's collected and what's missing
    print(f"DEBUG: Collected data: {collected_data}")
    print(f"DEBUG: Missing fields: {missing_fields}")
    
    bot_response = ""
    if gemini_service:
        try:
            bot_response = gemini_service.generate_conversational_response(
                current_step,
                chat_msg.message,
                collected_data,
                history_list,
                conversation_summary,
                missing_fields
            )
            # Strip markdown formatting from response
            import re
            bot_response = re.sub(r'\*\*([^*]+)\*\*', r'\1', bot_response)  # Remove **bold**
            bot_response = re.sub(r'\*([^*]+)\*', r'\1', bot_response)  # Remove *italic*
            bot_response = re.sub(r'`([^`]+)`', r'\1', bot_response)  # Remove `code`
            bot_response = re.sub(r'#+\s*', '', bot_response)  # Remove headers
            bot_response = bot_response.strip()
        except Exception as e:
            error_msg = str(e).lower()
            if '429' in error_msg or 'rate limit' in error_msg or 'quota' in error_msg:
                print(f"Gemini API rate limit (429) - using fallback response")
            else:
                print(f"Error generating AI response: {e}")
            # Always use fallback on error (especially for 429 rate limits)
            bot_response = get_fallback_response(current_step, collected_data, missing_fields)
    else:
        bot_response = get_fallback_response(current_step, collected_data, missing_fields)
    
    conv = Conversation(
        user_id=state.user_id,
        plan_id=state.plan_id,
        message=chat_msg.message,
        response=bot_response,
        message_type='user_input'
    )
    db.add(conv)
    
    state.collected_data = collected_data
    state.current_step = current_step
    db.commit()
    
    return ChatResponse(
        response=bot_response,
        current_step=current_step,
        collected_data=collected_data,
        is_complete=False
    )

async def handle_followup_question(chat_msg: ChatMessage, state: ConversationState, db: Session) -> ChatResponse:
    """Handle follow-up questions after plan is generated."""
    user = db.query(User).filter(User.id == state.user_id).first()
    plan = db.query(UserPlan).filter(UserPlan.id == state.plan_id).first()
    
    if not user or not plan:
        raise HTTPException(status_code=404, detail="User or plan not found")
    
    history = db.query(Conversation).filter(
        Conversation.user_id == state.user_id,
        Conversation.plan_id == state.plan_id
    ).order_by(Conversation.created_at.desc()).limit(10).all()
    
    history_list = [
        {"message": conv.message, "response": conv.response}
        for conv in reversed(history)
    ]
    
    user_data = {
        'name': user.name,
        'goal': user.goal,
        'diet_type': user.diet_type,
        'food_allergies': user.food_allergies or '',
        'disliked_foods': user.disliked_foods or '',
        'workout_experience': user.workout_experience,
        'workout_days_per_week': user.workout_days_per_week
    }
    
    bot_response = ""
    if gemini_service:
        try:
            bot_response = gemini_service.answer_followup_question(
                user_data,
                plan.diet_plan,
                plan.workout_plan,
                chat_msg.message,
                history_list
            )
        except:
            bot_response = "I'm here to help! What would you like to know about your plan?"
    else:
        bot_response = "I'm here to help! What would you like to know about your plan?"
    
    conv = Conversation(
        user_id=state.user_id,
        plan_id=state.plan_id,
        message=chat_msg.message,
        response=bot_response,
        message_type='followup'
    )
    db.add(conv)
    db.commit()
    
    return ChatResponse(
        response=bot_response,
        current_step='complete',
        collected_data=state.collected_data or {},
        is_complete=True,
        plan_generated=True,
        user_id=state.user_id,
        plan_id=state.plan_id,
        diet_plan=plan.diet_plan,
        workout_plan=plan.workout_plan
    )

@app.post("/api/users", status_code=status.HTTP_201_CREATED)
async def create_user_and_plan(user_input: UserInput, db: Session = Depends(get_db)):
    """
    Create a new user and generate their personalized diet and workout plan.
    """
    try:
        # Validate target weight for non-maintenance goals
        if user_input.goal_planning.goal != 'maintenance' and not user_input.goal_planning.target_weight:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target weight is required for fat_loss and muscle_gain goals"
            )
        
        # Safety check: Validate target weight is realistic
        if user_input.goal_planning.target_weight:
            current_weight = user_input.personal_details.weight
            target = user_input.goal_planning.target_weight
            goal = user_input.goal_planning.goal
            
            if goal == 'fat_loss' and target >= current_weight:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Target weight must be less than current weight for fat loss"
                )
            if goal == 'muscle_gain' and target <= current_weight:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Target weight must be greater than current weight for muscle gain"
                )
        
        # Create user record
        user_data = {
            'name': user_input.personal_details.name,
            'age': user_input.personal_details.age,
            'gender': user_input.personal_details.gender,
            'height': user_input.personal_details.height,
            'weight': user_input.personal_details.weight,
            'goal': user_input.goal_planning.goal,
            'target_weight': user_input.goal_planning.target_weight,
            'medical_conditions': user_input.health_constraints.medical_conditions,
            'food_allergies': user_input.health_constraints.food_allergies,
            'diet_type': user_input.health_constraints.diet_type,
            'disliked_foods': user_input.health_constraints.disliked_foods,
            'meals_per_day': user_input.eating_habits.meals_per_day,
            'cooking_habits': user_input.eating_habits.cooking_habits,
            'wake_time': user_input.lifestyle.wake_time,
            'sleep_time': user_input.lifestyle.sleep_time,
            'work_hours': user_input.lifestyle.work_hours,
            'activity_level': user_input.lifestyle.activity_level,
            'workout_experience': user_input.workout_info.workout_experience,
            'workout_days_per_week': user_input.workout_info.workout_days_per_week,
            'workout_duration': user_input.workout_info.workout_duration
        }
        
        db_user = User(**user_data)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        # Generate plans using core logic
        diet_plan = DietPlanGenerator.generate_weekly_meal_plan(user_data)
        workout_plan = WorkoutPlanGenerator.generate_weekly_workout_plan(user_data)
        
        # Generate explanation using AI
        explanation = ""
        if gemini_service:
            try:
                explanation = gemini_service.generate_plan_explanation(user_data, diet_plan, workout_plan)
            except Exception as e:
                print(f"Error generating explanation: {e}")
                explanation = f"Your personalized plan has been created based on your goal of {user_data['goal']}, {user_data['diet_type']} diet preferences, and {user_data['workout_experience']} workout experience level."
        else:
            explanation = f"Your personalized plan has been created based on your goal of {user_data['goal']}, {user_data['diet_type']} diet preferences, and {user_data['workout_experience']} workout experience level."
        
        # Save plan to database
        db_plan = UserPlan(
            user_id=db_user.id,
            diet_plan=diet_plan,
            workout_plan=workout_plan,
            explanation=explanation
        )
        db.add(db_plan)
        db.commit()
        db.refresh(db_plan)
        
        return {
            "user_id": db_user.id,
            "plan_id": db_plan.id,
            "diet_plan": diet_plan,
            "workout_plan": workout_plan,
            "explanation": explanation,
            "message": "Plan generated successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating plan: {str(e)}"
        )

@app.get("/api/users/{user_id}/plan")
async def get_user_plan(user_id: int, db: Session = Depends(get_db)):
    """Get the latest plan for a user."""
    plan = db.query(UserPlan).filter(UserPlan.user_id == user_id).order_by(UserPlan.created_at.desc()).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found for this user"
        )
    
    return {
        "user_id": user_id,
        "plan_id": plan.id,
        "diet_plan": plan.diet_plan,
        "workout_plan": plan.workout_plan,
        "explanation": plan.explanation,
        "created_at": plan.created_at
    }

@app.post("/api/conversations")
async def ask_followup_question(question: FollowUpQuestion, db: Session = Depends(get_db)):
    """Handle follow-up questions about the plan."""
    # Get user and plan
    user = db.query(User).filter(User.id == question.user_id).first()
    plan = db.query(UserPlan).filter(UserPlan.id == question.plan_id).first()
    
    if not user or not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User or plan not found"
        )
    
    # Get conversation history
    history = db.query(Conversation).filter(
        Conversation.user_id == question.user_id,
        Conversation.plan_id == question.plan_id
    ).order_by(Conversation.created_at.desc()).limit(10).all()
    
    history_list = [
        {"message": conv.message, "response": conv.response}
        for conv in reversed(history)
    ]
    
    # Prepare user data
    user_data = {
        'goal': user.goal,
        'diet_type': user.diet_type,
        'food_allergies': user.food_allergies or '',
        'disliked_foods': user.disliked_foods or '',
        'workout_experience': user.workout_experience,
        'workout_days_per_week': user.workout_days_per_week
    }
    
    # Generate response using AI
    if gemini_service:
        try:
            response = gemini_service.answer_followup_question(
                user_data,
                plan.diet_plan,
                plan.workout_plan,
                question.question,
                history_list
            )
        except Exception as e:
            response = "I apologize, but I'm having trouble processing your question right now. Please try again."
    else:
        response = "AI service is not available. Please contact support for assistance."
    
    # Save conversation
    conversation = Conversation(
        user_id=question.user_id,
        plan_id=question.plan_id,
        message=question.question,
        response=response
    )
    db.add(conversation)
    db.commit()
    
    return {
        "response": response,
        "conversation_id": conversation.id
    }

@app.get("/api/conversations/{user_id}/{plan_id}")
async def get_conversation_history(user_id: int, plan_id: int, db: Session = Depends(get_db)):
    """Get conversation history for a user's plan."""
    conversations = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.plan_id == plan_id
    ).order_by(Conversation.created_at.asc()).all()
    
    return [
        {
            "id": conv.id,
            "message": conv.message,
            "response": conv.response,
            "created_at": conv.created_at
        }
        for conv in conversations
    ]

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "gemini_available": gemini_service is not None
    }

if __name__ == "__main__":
    import sys
    import os
    
    # Check if running from correct directory
    if not os.path.exists('app') and os.path.basename(os.getcwd()) == 'app':
        print("ERROR: Please run this script from the project root directory, not from inside the 'app' folder.")
        print("Correct way: python app/main.py (from project root)")
        print("Or use: python run.py (from project root)")
        sys.exit(1)
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

