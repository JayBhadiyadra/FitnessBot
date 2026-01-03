"""
FastAPI main application with LangChain agent integration for the fitness chatbot.
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import uuid
import os

from app.database import get_db, engine, Base
from app.models import User, UserPlan, Conversation, ConversationState
from app.schemas import UserInput, FollowUpQuestion, ChatMessage, ChatResponse
from app.core_logic import DietPlanGenerator, WorkoutPlanGenerator
from app.langchain_service import LangChainFitnessAgent

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fitness Plan Chatbot API",
    description="Personalized Diet & Workout Plan Chatbot with LangChain Agent",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    """Start a new conversation session with LangChain agent."""
    session_id = str(uuid.uuid4())
    
    # Create conversation state
    state = ConversationState(
        session_id=session_id,
        current_step='personal_details',
        collected_data={},
        is_complete=0
    )
    db.add(state)
    db.commit()
    
    # Initialize LangChain agent
    try:
        agent = LangChainFitnessAgent(db, session_id)
        initial_message = agent.process_message("", [])
    except Exception as e:
        print(f"Error initializing LangChain agent: {e}")
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

@app.post("/api/chat/message", response_model=ChatResponse)
async def handle_chat_message(chat_msg: ChatMessage, db: Session = Depends(get_db)):
    """Handle a chat message using LangChain agent."""
    state = db.query(ConversationState).filter(
        ConversationState.session_id == chat_msg.session_id
    ).first()
    
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found. Please start a new conversation."
        )
    
    # If plan is already generated, handle as follow-up question
    if state.is_complete == 1:
        return await handle_followup_question(chat_msg, state, db)
    
    # Get conversation history
    history = db.query(Conversation).filter(
        Conversation.user_id == (state.user_id if state.user_id else None)
    ).order_by(Conversation.created_at.desc()).limit(10).all()
    
    history_list = [
        {"message": conv.message, "response": conv.response}
        for conv in reversed(history)
    ]
    
    # Initialize LangChain agent for this session
    try:
        agent = LangChainFitnessAgent(db, chat_msg.session_id)
        
        # Process message through LangChain agent
        bot_response = agent.process_message(chat_msg.message, history_list)
        
        # Refresh state to get updated data
        db.refresh(state)
        collected_data = state.collected_data or {}
        current_step = state.current_step
        
        # Check if plan was generated (agent called generate_fitness_plan tool)
        if state.is_complete == 1:
            # Plan was generated - fetch it
            plan = db.query(UserPlan).filter(UserPlan.id == state.plan_id).first()
            user = db.query(User).filter(User.id == state.user_id).first()
            
            if plan and user:
                # Save conversation
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
                    current_step='complete',
                    collected_data=collected_data,
                    is_complete=True,
                    plan_generated=True,
                    user_id=state.user_id,
                    plan_id=state.plan_id,
                    diet_plan=plan.diet_plan,
                    workout_plan=plan.workout_plan
                )
        
        # Save conversation
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
            is_complete=False,
            plan_generated=False
        )
        
    except Exception as e:
        print(f"Error in LangChain agent: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback response - user-friendly error message
        bot_response = "I apologize, I encountered an error processing your message. Please try again or rephrase your question."
        
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
            current_step=state.current_step,
            collected_data=state.collected_data or {},
            is_complete=False
        )

async def handle_followup_question(chat_msg: ChatMessage, state: ConversationState, db: Session) -> ChatResponse:
    """Handle follow-up questions after plan is generated using LangChain agent."""
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
    
    # Use LangChain agent for follow-up questions
    try:
        agent = LangChainFitnessAgent(db, chat_msg.session_id)
        bot_response = agent.answer_followup_question(
            chat_msg.message,
            user_data,
            plan.diet_plan,
            plan.workout_plan,
            history_list
        )
    except Exception as e:
        print(f"Error in LangChain agent for follow-up: {e}")
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
    (Alternative endpoint - not used by frontend chat interface)
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
        
        # Generate explanation using LangChain agent
        explanation = ""
        try:
            session_id = str(uuid.uuid4())
            agent = LangChainFitnessAgent(db, session_id)
            explanation = agent._generate_plan_explanation(user_data, diet_plan, workout_plan)
        except Exception as e:
            print(f"Error generating explanation: {e}")
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
    """Handle follow-up questions about the plan (alternative endpoint)."""
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
        'name': user.name,
        'goal': user.goal,
        'diet_type': user.diet_type,
        'food_allergies': user.food_allergies or '',
        'disliked_foods': user.disliked_foods or '',
        'workout_experience': user.workout_experience,
        'workout_days_per_week': user.workout_days_per_week
    }
    
    # Generate response using LangChain agent
    try:
        session_id = str(uuid.uuid4())
        agent = LangChainFitnessAgent(db, session_id)
        response = agent.answer_followup_question(
            question.question,
            user_data,
            plan.diet_plan,
            plan.workout_plan,
            history_list
        )
    except Exception as e:
        print(f"Error generating response: {e}")
        response = "I apologize, but I'm having trouble processing your question right now. Please try again."
    
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
    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        langchain_available = api_key is not None
    except:
        langchain_available = False
    
    return {
        "status": "healthy",
        "langchain_available": langchain_available,
        "version": "2.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
