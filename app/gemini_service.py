"""
Gemini AI service for generating explanations and handling follow-up questions.
AI is only used for explanations, not for plan generation.
"""
import os
import json
import google.generativeai as genai
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from app.conversation_flow import ConversationFlow

load_dotenv()

class GeminiService:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        # Validate API key format (should start with AIza)
        if not api_key.startswith("AIza"):
            print(f"Warning: API key format looks unusual. Expected to start with 'AIza'")
        
        # Get model name from env or use default
        # Use gemini-2.5-flash as default (most compatible with free tier)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        
        print(f"Initializing Gemini service with model: {model_name}")
        print(f"API Key loaded: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else '***'}")
        
        genai.configure(api_key=api_key)
        
        # Try to initialize the model with error handling and fallbacks
        model_initialized = False
        try:
            self.model = genai.GenerativeModel(model_name)
            print(f"✓ Successfully initialized Gemini model: {model_name}")
            model_initialized = True
        except Exception as e:
            error_str = str(e)
            print(f"⚠ Error initializing model {model_name}: {error_str[:200]}")
            
            # Try fallback models in order of compatibility (free tier)
            fallback_models = ['gemini-2.5-flash', 'models/gemini-2.5-flash']
            
            for fallback_model in fallback_models:
                try:
                    print(f"  Trying fallback model: {fallback_model}")
                    self.model = genai.GenerativeModel(fallback_model)
                    print(f"  ✓ Successfully initialized with fallback: {fallback_model}")
                    model_name = fallback_model  # Update to the working model
                    model_initialized = True
                    break
                except Exception as fallback_error:
                    print(f"  ✗ {fallback_model} failed: {str(fallback_error)[:100]}")
                    continue
            
            if not model_initialized:
                raise ValueError(f"Could not initialize any Gemini model. Tried: {model_name}, {', '.join(fallback_models)}. Please check your API key and available models. For free tier, use 'gemini-2.5-flash'.")
        
        self.api_key = api_key
        self.model_name = model_name
    
    def generate_plan_explanation(
        self,
        user_data: Dict[str, Any],
        diet_plan: Dict[str, Any],
        workout_plan: Dict[str, Any]
    ) -> str:
        """Generate a human-readable explanation of the generated plan."""
        
        prompt = f"""You are a fitness and nutrition expert. Explain the personalized diet and workout plan that was generated for a user.

User Profile:
- Name: {user_data.get('name', 'User')}
- Age: {user_data.get('age')} years
- Gender: {user_data.get('gender')}
- Height: {user_data.get('height')} cm
- Weight: {user_data.get('weight')} kg
- Goal: {user_data.get('goal')}
- Target Weight: {user_data.get('target_weight', 'N/A')} kg
- Activity Level: {user_data.get('activity_level')}
- Workout Experience: {user_data.get('workout_experience')}
- Diet Type: {user_data.get('diet_type')}
- Meals per day: {user_data.get('meals_per_day')}
- Workout days per week: {user_data.get('workout_days_per_week')}
- Workout duration: {user_data.get('workout_duration')} minutes

Daily Nutritional Targets:
- Calories: {diet_plan.get('daily_targets', {}).get('calories')} kcal
- Protein: {diet_plan.get('daily_targets', {}).get('macros', {}).get('protein')}g
- Carbs: {diet_plan.get('daily_targets', {}).get('macros', {}).get('carbs')}g
- Fats: {diet_plan.get('daily_targets', {}).get('macros', {}).get('fats')}g

Please provide a clear, friendly explanation that:
1. Explains why this specific plan was created for this user
2. How the plan aligns with their goal ({user_data.get('goal')})
3. Highlights key features of the diet plan (considering their diet type, allergies, and preferences)
4. Explains the workout structure and why it's appropriate for their experience level
5. Provides motivation and encouragement

Keep it concise (2-3 paragraphs), professional, and easy to understand. Do not make medical claims.
"""
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_msg = str(e).lower()
            if '429' in error_msg or 'rate limit' in error_msg or 'quota' in error_msg:
                print(f"Gemini API rate limit (429) - using detailed fallback explanation")
            else:
                print(f"Error generating plan explanation: {e}")
            # Generate a more detailed fallback explanation
            goal_text = user_data.get('goal', 'your fitness').replace('_', ' ')
            diet_type_text = user_data.get('diet_type', 'your preferred').replace('_', ' ')
            return f"""Great news! I've created a personalized fitness plan tailored specifically for you.

**About Your Plan:**
Your daily nutrition targets {diet_plan.get('daily_targets', {}).get('calories')} calories, with a balanced macronutrient breakdown of {diet_plan.get('daily_targets', {}).get('macros', {}).get('protein')}g protein, {diet_plan.get('daily_targets', {}).get('macros', {}).get('carbs')}g carbohydrates, and {diet_plan.get('daily_targets', {}).get('macros', {}).get('fats')}g fats. This is optimized for your {goal_text} goal.

**Workout Schedule:**
Your workout plan includes {user_data.get('workout_days_per_week')} sessions per week, each lasting {user_data.get('workout_duration')} minutes. The exercises are designed for your {user_data.get('workout_experience')} experience level, ensuring you can perform them safely and effectively.

**Diet Considerations:**
The meal plan is customized for your {diet_type_text} diet preferences, taking into account your food allergies and dislikes to ensure you enjoy every meal while staying on track.

This plan is designed to help you achieve your {goal_text} goal while maintaining a healthy, sustainable approach. Feel free to ask me any questions about your plan!"""
    
    def get_conversational_prompt(
        self,
        step: str,
        collected_data: Dict[str, Any],
        conversation_history: Optional[list] = None
    ) -> str:
        """Generate an engaging conversational prompt for data collection."""
        
        history_context = ""
        if conversation_history:
            recent_msgs = conversation_history[-3:]  # Last 3 messages for context
            history_context = "\nRecent conversation:\n" + "\n".join([
                f"User: {msg.get('message', '')}\nYou: {msg.get('response', '')}"
                for msg in recent_msgs
            ])
        
        step_prompts = {
            'personal_details': f"""You are a friendly and enthusiastic fitness coach chatbot. You're collecting information from a user to create their personalized fitness plan.

{history_context}

Data already collected: {collected_data}

The user needs to provide: name, age, gender, height (in cm), and weight (in kg).

IMPORTANT: 
- Ask for ONE piece of information at a time. Do NOT ask for multiple things in one message.
- If the user just provided information, acknowledge it warmly and ask for the NEXT single piece of information.
- Do NOT ask for information that is already in collected_data.
- Ask in this order: name → age → gender → height → weight (one at a time).

Be conversational, friendly, and encouraging. After getting each piece of information, acknowledge it positively and naturally move to the next question.

Remember: All numeric values (age, height, weight) must be positive numbers (greater than 0). If user enters 0 or negative, politely ask them to enter a positive number.

Keep your responses short (1-2 sentences) and engaging. End with a question about the NEXT single piece of information needed.
DO NOT use markdown formatting - use plain text only.""",

            'goal_planning': f"""You are a friendly fitness coach chatbot. You've collected the user's basic info. Now you need to know their fitness goal and target weight.

{history_context}

Collected so far: {collected_data.get('name', 'User')} is {collected_data.get('age')} years old, {collected_data.get('gender')}, {collected_data.get('height')} cm tall, {collected_data.get('weight')} kg.

Ask about their goal (fat loss, muscle gain, or maintenance) and target weight (if applicable). Be encouraging and help them think about realistic goals. If they choose fat_loss or muscle_gain, target weight is required.

Remember: Target weight must be a positive number. If user enters 0 or negative, politely ask for a positive number.

Keep responses conversational and motivating. End with an engaging question.""",

            'health_constraints': f"""You are a friendly fitness coach chatbot. Now you need to know about their health constraints and dietary preferences.

{history_context}

Data already collected: {collected_data}

Ask about: medical conditions (optional), food allergies, diet type (vegetarian/non-vegetarian/vegan/pescatarian), and disliked foods. 

IMPORTANT: 
- Ask for ONE piece of information at a time.
- If diet_type is already in collected_data, DO NOT ask for it again - move to the next field.
- If the user just provided their diet type, acknowledge it and move to asking about food allergies or disliked foods.
- Be understanding and non-judgmental. Make them feel comfortable sharing this information.

Keep it conversational and supportive. End with a question about the NEXT piece of information needed.""",

            'eating_lifestyle': f"""You are a friendly fitness coach chatbot. Now you need to know about their eating habits and lifestyle.

{history_context}

Ask about: meals per day, cooking habits, wake time, sleep time, work hours, and activity level. Make it feel natural and conversational.

Remember: Meals per day must be a positive number (2-6). If user enters 0 or negative, politely ask for a positive number.

Keep responses engaging. End with a question to maintain conversation flow.""",

            'workout_info': f"""You are a friendly fitness coach chatbot. This is the final step! You need workout information.

{history_context}

Ask about: workout experience (beginner/intermediate/advanced), workout days per week, and workout duration in minutes.

Remember: Workout days and duration must be positive numbers. If user enters 0 or negative, politely ask for a positive number.

Be enthusiastic - they're almost done! Keep it conversational and motivating. End with an engaging question."""
        }
        
        return step_prompts.get(step, "Continue the conversation naturally and engagingly.")
    
    def generate_conversational_response(
        self,
        step: str,
        user_message: str,
        collected_data: Dict[str, Any],
        conversation_history: Optional[list] = None,
        conversation_summary: Optional[str] = None,
        missing_fields: Optional[list] = None
    ) -> str:
        """Generate an engaging conversational response for data collection."""
        prompt = self.get_conversational_prompt(step, collected_data, conversation_history)
        
        # Determine what was just collected by comparing with what's needed
        step_fields = ConversationFlow.STEP_FIELDS.get(step, [])
        missing_before = []
        collected_now = []
        
        # This is a simplified check - in reality we'd need to track previous state
        # For now, we'll explicitly tell the AI what's in collected_data
        
        # Build context information
        summary_text = conversation_summary or "No information collected yet."
        missing_text = ""
        if missing_fields:
            missing_text = f"\n\nFields still needed for this step: {', '.join(missing_fields)}"
        
        full_prompt = f"""{prompt}

CONVERSATION SUMMARY:
{summary_text}
{missing_text}

User just said: "{user_message}"

CURRENT STATUS - Data already collected:
{json.dumps(collected_data, indent=2)}

CRITICAL INSTRUCTIONS - READ CAREFULLY:
1. DO NOT ask for information that is already in the collected_data above. Check the summary and collected_data carefully.
2. If the user just provided information (and it's now in collected_data), you MUST:
   - Acknowledge it warmly and positively
   - Move immediately to asking for the NEXT missing field
   - DO NOT repeat the same question
3. Use the conversation summary to remember what has been asked and answered.
4. If a field is in collected_data, it means the user has already provided it - DO NOT ask again.
5. Only ask for fields that are in the "Fields still needed" list above.
6. Keep responses short (1-2 sentences), friendly, and engaging.
7. Always end with a question about the NEXT piece of information needed (from the missing fields list).
8. DO NOT use markdown formatting (no **bold**, *italic*, `code`, or # headers) - use plain text only.

Example: If name is in collected_data, say "Nice to meet you, [name]! How old are you?" (NOT "What's your name?" again)."""
        
        try:
            response = self.model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            print(f"Error generating AI response: {e}")
            # Use missing fields to provide appropriate fallback
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
            if step == 'personal_details':
                if collected_data.get('name') and not collected_data.get('age'):
                    return f"Nice to meet you, {collected_data.get('name')}! How old are you?"
                elif collected_data.get('age') and not collected_data.get('gender'):
                    return f"Great! What's your gender - male, female, or other?"
                elif collected_data.get('gender') and not collected_data.get('height'):
                    return "Perfect! What's your height in centimeters?"
                elif collected_data.get('height') and not collected_data.get('weight'):
                    return "Thanks! What's your current weight in kilograms?"
                else:
                    return "Great! Let's get started. What's your name?"
            elif step == 'goal_planning':
                if collected_data.get('goal') and not collected_data.get('target_weight'):
                    if collected_data.get('goal') != 'maintenance':
                        return f"Excellent! What's your target weight in kilograms?"
                    else:
                        return "Perfect! Moving on..."
                else:
                    return "What's your fitness goal - fat loss, muscle gain, or maintenance?"
            elif step == 'health_constraints':
                return "Do you have any food allergies I should know about?"
            elif step == 'eating_lifestyle':
                return "How many meals do you typically eat per day?"
            elif step == 'workout_info':
                return "What's your workout experience level - beginner, intermediate, or advanced?"
            else:
                return "Please continue..."
    
    def answer_followup_question(
        self,
        user_data: Dict[str, Any],
        diet_plan: Dict[str, Any],
        workout_plan: Dict[str, Any],
        question: str,
        conversation_history: Optional[list] = None
    ) -> str:
        """Answer follow-up questions about the plan with engaging, context-aware responses."""
        
        history_context = ""
        if conversation_history:
            history_context = "\nPrevious conversation:\n" + "\n".join([
                f"User: {msg.get('message', '')}\nAssistant: {msg.get('response', '')}"
                for msg in conversation_history[-5:]  # Last 5 messages
            ])
        
        # Format diet plan for context
        diet_context = ""
        if diet_plan:
            daily_targets = diet_plan.get('daily_targets', {})
            diet_context = f"""
Daily Nutritional Targets:
- Calories: {daily_targets.get('calories', 'N/A')} kcal
- Protein: {daily_targets.get('macros', {}).get('protein', 'N/A')}g
- Carbs: {daily_targets.get('macros', {}).get('carbs', 'N/A')}g
- Fats: {daily_targets.get('macros', {}).get('fats', 'N/A')}g

Weekly Meal Plan Summary:
"""
            weekly_plan = diet_plan.get('weekly_plan', {})
            for day, day_plan in weekly_plan.items():
                if day_plan and day_plan.get('meals'):
                    meals = ", ".join([f"{m.get('meal_type')}: {m.get('food')}" for m in day_plan.get('meals', [])])
                    diet_context += f"- {day}: {meals}\n"
        
        # Format workout plan for context
        workout_context = ""
        if workout_plan:
            workout_context = f"""
Workout Plan Summary:
- Total Workout Days: {workout_plan.get('total_workout_days', 'N/A')} days per week
- Session Duration: {workout_plan.get('session_duration', 'N/A')} minutes
- Recovery Guidance: {workout_plan.get('recovery_guidance', 'N/A')}

Weekly Schedule:
"""
            weekly_plan = workout_plan.get('weekly_plan', {})
            for day, day_plan in weekly_plan.items():
                if day_plan:
                    exercises = day_plan.get('exercises', [])
                    if isinstance(exercises, list):
                        exercises_str = ", ".join(exercises)
                    else:
                        exercises_str = str(exercises)
                    workout_context += f"- {day}: {day_plan.get('type', 'Rest')} - {exercises_str} ({day_plan.get('duration_minutes', 0)} min)\n"
        
        prompt = f"""You are an enthusiastic, friendly, and knowledgeable fitness and nutrition coach. Answer the user's question about their personalized plan in an engaging, conversational way. You have access to their complete plan details.

User's Profile:
- Name: {user_data.get('name', 'User')}
- Goal: {user_data.get('goal')}
- Diet Type: {user_data.get('diet_type')}
- Allergies: {user_data.get('food_allergies', 'None')}
- Disliked Foods: {user_data.get('disliked_foods', 'None')}
- Workout Experience: {user_data.get('workout_experience')}
- Workout Days: {user_data.get('workout_days_per_week')} days per week

{diet_context}

{workout_context}

{history_context}

User's Question: {question}

IMPORTANT INSTRUCTIONS:
1. You can see their complete diet and workout plan above. Use this information to answer questions accurately.
2. If they ask to modify the plan (e.g., "Can I replace X with Y?", "I don't like this exercise", "Can I change Monday's meal?"), provide specific suggestions based on their plan.
3. For food swaps: Suggest alternatives that match their diet type ({user_data.get('diet_type')}) and avoid their allergies ({user_data.get('food_allergies', 'None')}) and disliked foods ({user_data.get('disliked_foods', 'None')}).
4. For workout modifications: Consider their experience level ({user_data.get('workout_experience')}) and provide safe alternatives.
5. Be conversational, friendly, and encouraging (2-3 sentences).
6. Always end with an open-ended question to keep the conversation going.
7. DO NOT use markdown formatting (no **bold**, *italic*, `code`, or # headers) - use plain text only.
8. Do not make medical claims. If asked about medical conditions, recommend consulting a healthcare professional.

Example responses:
- "I'd love to help you swap that! For Monday's lunch, you could replace [current food] with [alternative] which fits your vegetarian diet perfectly. Would you like more options for that day?"
- "Absolutely! Instead of [exercise], you could try [alternative] which is great for beginners. How does that sound?"
"""
        
        try:
            response = self.model.generate_content(prompt)
            # Strip markdown formatting
            import re
            response_text = response.text
            response_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', response_text)  # Remove **bold**
            response_text = re.sub(r'\*([^*]+)\*', r'\1', response_text)  # Remove *italic*
            response_text = re.sub(r'`([^`]+)`', r'\1', response_text)  # Remove `code`
            response_text = re.sub(r'#+\s*', '', response_text)  # Remove headers
            return response_text.strip()
        except Exception as e:
            print(f"Error generating follow-up response: {e}")
            return "I apologize, but I'm having trouble processing your question right now. What else can I help you with?"

