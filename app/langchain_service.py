"""
LangChain Agent Service for Fitness Chatbot

This service replaces the manual conversation flow with a LangChain agent
that uses tools for data collection, validation, and plan generation.
"""

import os
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

from app.core_logic import DietPlanGenerator, WorkoutPlanGenerator
from app.conversation_flow import ConversationFlow
from app.models import User, UserPlan, Conversation, ConversationState

load_dotenv()


class LangChainFitnessAgent:
    """LangChain agent for fitness chatbot conversation flow."""
    
    def __init__(self, db: Session, session_id: str):
        self.db = db
        self.session_id = session_id
        self.llm = None
        self.agent_executor = None
        self._initialize_llm()
        self._create_agent()
    
    def _initialize_llm(self):
        """Initialize the Gemini LLM."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        try:
            system_instruction = """You are a friendly and conversational fitness coach assistant. Your job is to collect user information ONE field at a time to create a personalized fitness plan.

CRITICAL RULES:
1. Ask for ONLY ONE field at a time. Never ask for multiple fields in a single question.
2. Be natural and conversational. For example, ask "What's your name?" instead of "Please provide your name, age, gender, height, and weight."
3. After the user provides a value, use validate_and_save_field to save it, then use check_missing_fields to find the next field to ask.
4. The check_missing_fields tool returns only ONE field - ask for that field only.
5. Be friendly, encouraging, and patient. Make the conversation feel natural, not like a form.
6. After collecting all required data, use generate_fitness_plan to create the plan."""
            
            self.llm = ChatGoogleGenerativeAI(
                model=os.getenv("MODEL", "gemini-2.5-flash"),
                google_api_key=api_key,
                temperature=0.7,
                system_instruction=system_instruction
            )
        except Exception as e:
            raise ValueError(f"Failed to initialize LLM: {e}")
    
    def _get_state(self) -> ConversationState:
        """Get the conversation state for this session."""
        state = self.db.query(ConversationState).filter(
            ConversationState.session_id == self.session_id
        ).first()
        if not state:
            raise ValueError(f"Session {self.session_id} not found")
        return state
    
    def _create_tools(self) -> List[Tool]:
        """Create LangChain tools for the fitness chatbot."""
        
        def validate_and_save_field(input_str: str) -> str:
            """
            Validate a field value and save it to conversation state.
            Accepts input as JSON string: {"field_name": "name", "field_value": "John"}
            """
            import json
            import re
            try:
                # Parse the input - could be JSON string or dict
                if isinstance(input_str, dict):
                    data = input_str
                elif isinstance(input_str, str):
                    # Try to parse as JSON first
                    try:
                        data = json.loads(input_str)
                    except json.JSONDecodeError:
                        # If not valid JSON, try to extract from string patterns
                        # Pattern 1: field_name="name" field_value="John"
                        # Pattern 2: 'field_name': 'name', 'field_value': 'John'
                        # Pattern 3: field_name: name, field_value: John
                        
                        # Try to find field_name (must be a single word/identifier)
                        field_name_patterns = [
                            r'"field_name"\s*:\s*"([^"]+)"',
                            r"'field_name'\s*:\s*'([^']+)'",
                            r'field_name["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)'
                        ]
                        # Try to find field_value (can contain spaces, so look for quoted strings first)
                        field_value_patterns = [
                            r'"field_value"\s*:\s*"([^"]+)"',
                            r"'field_value'\s*:\s*'([^']+)'",
                            r'field_value["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)'
                        ]
                        
                        field_name = None
                        field_value = None
                        
                        for pattern in field_name_patterns:
                            match = re.search(pattern, input_str, re.IGNORECASE)
                            if match:
                                field_name = match.group(1).strip('"\'')
                                break
                        
                        for pattern in field_value_patterns:
                            match = re.search(pattern, input_str, re.IGNORECASE)
                            if match:
                                field_value = match.group(1).strip('"\'')
                                break
                        
                        if field_name and field_value is not None:
                            data = {"field_name": field_name, "field_value": field_value}
                        else:
                            return f"Error: Could not parse field_name and field_value from input. Expected JSON format: {{\"field_name\": \"name\", \"field_value\": \"John\"}}. Got: {input_str}"
                else:
                    return f"Error: Invalid input type. Expected string or dict. Got: {type(input_str)}"
                
                field_name = data.get("field_name")
                field_value = data.get("field_value")
                
                if not field_name:
                    return "Error: field_name is required"
                if field_value is None:
                    return "Error: field_value is required"
                
                state = self._get_state()
                
                # Validate the field
                is_valid, error_msg = ConversationFlow.validate_field(
                    field_name, field_value, state.current_step
                )
                
                if not is_valid:
                    return f"Validation error: {error_msg}"
                
                # Convert and normalize value
                collected_data = state.collected_data or {}
                
                try:
                    if field_name in ['age', 'meals_per_day', 'workout_days_per_week', 'workout_duration']:
                        collected_data[field_name] = int(float(field_value))
                    elif field_name in ['height', 'weight', 'target_weight']:
                        collected_data[field_name] = float(field_value)
                    elif field_name == 'diet_type':
                        # Normalize diet_type
                        value_lower = str(field_value).lower().strip()
                        if 'vegan' in value_lower:
                            collected_data[field_name] = 'vegan'
                        elif 'pescatarian' in value_lower or 'pesca' in value_lower:
                            collected_data[field_name] = 'pescatarian'
                        elif any(word in value_lower for word in ['non', 'meat', 'chicken']) or 'non-veg' in value_lower:
                            collected_data[field_name] = 'non_veg'
                        elif any(word in value_lower for word in ['veg', 'vegetarian']):
                            collected_data[field_name] = 'veg'
                        else:
                            collected_data[field_name] = str(field_value).strip()
                    else:
                        collected_data[field_name] = str(field_value).strip()
                    
                    # Update state
                    state.collected_data = collected_data
                    self.db.commit()
                    
                    return f"Successfully saved {field_name}: {collected_data[field_name]}"
                except (ValueError, TypeError) as e:
                    return f"Error processing {field_name}: {str(e)}"
            except Exception as e:
                return f"Error parsing input: {str(e)}. Expected JSON format: {{\"field_name\": \"name\", \"field_value\": \"John\"}}"
        
        def check_missing_fields(*args, **kwargs) -> str:
            """Check which field should be asked next (returns only the FIRST missing field)."""
            state = self._get_state()
            collected_data = state.collected_data or {}
            current_step = state.current_step
            step_fields = ConversationFlow.STEP_FIELDS.get(current_step, [])
            
            # Find the FIRST missing required field
            for field in step_fields:
                if field not in collected_data or not collected_data[field]:
                    # Skip optional fields for now
                    if field not in ['medical_conditions', 'food_allergies', 'disliked_foods', 'target_weight']:
                        return f"Next field to ask: {field}"
            
            # If all required fields are collected, check if step is complete
            if ConversationFlow.is_step_complete(collected_data, current_step):
                next_step = ConversationFlow.get_next_step(current_step)
                if next_step:
                    state.current_step = next_step
                    self.db.commit()
                    # Find first missing field in next step
                    next_step_fields = ConversationFlow.STEP_FIELDS.get(next_step, [])
                    for field in next_step_fields:
                        if field not in collected_data or not collected_data[field]:
                            if field not in ['medical_conditions', 'food_allergies', 'disliked_foods', 'target_weight']:
                                return f"Step '{current_step}' complete! Moving to '{next_step}'. Next field: {field}"
                    return f"Step '{current_step}' complete! Moving to '{next_step}'."
                else:
                    # All steps complete
                    return "All steps complete! Ready to generate plan."
            else:
                # Step should be complete but isn't - check optional fields
                for field in step_fields:
                    if field not in collected_data or not collected_data[field]:
                        if field in ['medical_conditions', 'food_allergies', 'disliked_foods', 'target_weight']:
                            return f"Optional field available: {field} (you can ask about this or skip)"
                return f"Step '{current_step}' is complete."
            
            return "No missing fields found."
        
        def generate_fitness_plan(*args, **kwargs) -> str:
            """
            Generate a personalized fitness plan using core logic (NO LLM).
            This tool should only be called when all required data is collected.
            """
            state = self._get_state()
            collected_data = state.collected_data or {}
            
            # Check if all required fields are present
            required_fields = [
                'name', 'age', 'gender', 'height', 'weight', 'goal', 'diet_type',
                'meals_per_day', 'cooking_habits', 'wake_time', 'sleep_time',
                'work_hours', 'activity_level', 'workout_experience',
                'workout_days_per_week', 'workout_duration'
            ]
            
            missing = [f for f in required_fields if not collected_data.get(f)]
            if missing:
                return f"Missing required fields: {', '.join(missing)}. Please collect all data first."
            
            # Validate target_weight for non-maintenance goals
            if collected_data.get('goal') != 'maintenance' and not collected_data.get('target_weight'):
                return "Target weight is required for fat_loss and muscle_gain goals."
            
            # Generate plans using CORE LOGIC (NO LLM)
            try:
                diet_plan = DietPlanGenerator.generate_weekly_meal_plan(collected_data)
                workout_plan = WorkoutPlanGenerator.generate_weekly_workout_plan(collected_data)
                
                # Create user record
                user = User(**collected_data)
                self.db.add(user)
                self.db.commit()
                self.db.refresh(user)
                
                # Generate explanation using LLM (separate from plan generation)
                explanation = self._generate_plan_explanation(collected_data, diet_plan, workout_plan)
                
                # Save plan
                plan = UserPlan(
                    user_id=user.id,
                    diet_plan=diet_plan,
                    workout_plan=workout_plan,
                    explanation=explanation
                )
                self.db.add(plan)
                self.db.commit()
                self.db.refresh(plan)
                
                # Update state
                state.user_id = user.id
                state.plan_id = plan.id
                state.is_complete = 1
                self.db.commit()
                
                return f"Plan generated successfully! User ID: {user.id}, Plan ID: {plan.id}. The plan includes personalized diet and workout recommendations."
                
            except Exception as e:
                return f"Error generating plan: {str(e)}"
        
        def get_collected_data(*args, **kwargs) -> str:
            """Get summary of all collected data so far."""
            state = self._get_state()
            collected_data = state.collected_data or {}
            
            if not collected_data:
                return "No data collected yet."
            
            summary_parts = []
            for key, value in collected_data.items():
                if value:
                    summary_parts.append(f"{key}: {value}")
            
            return "Collected data:\n" + "\n".join(f"- {part}" for part in summary_parts)
        
        # Create tools
        tools = [
            Tool(
                name="validate_and_save_field",
                func=validate_and_save_field,
                description="""Validate a field value and save it to the conversation state.
                
                IMPORTANT: Use this tool to save ONE field at a time after the user provides it.
                Extract the field value from the user's message and save it using this tool.
                After saving, use check_missing_fields to find the next field to ask.
                
                Input format: JSON string with field_name and field_value
                Example: {"field_name": "name", "field_value": "John"}
                
                Available fields: name, age, gender, height, weight, goal, target_weight, diet_type, 
                food_allergies, disliked_foods, meals_per_day, cooking_habits, wake_time, sleep_time, 
                work_hours, activity_level, workout_experience, workout_days_per_week, workout_duration
                
                Returns:
                    Success message or validation error
                """
            ),
            Tool(
                name="check_missing_fields",
                func=check_missing_fields,
                description="""Check which field should be asked next (returns only ONE field at a time).
                
                IMPORTANT: This tool returns only the FIRST missing field. Ask the user for that ONE field only.
                After the user provides the value, use validate_and_save_field to save it, then call this tool again to get the next field.
                
                The tool will automatically move to the next step when the current step is complete.
                
                Returns:
                    The next field to ask (e.g., "Next field to ask: name") or confirmation that step is complete
                """
            ),
            Tool(
                name="generate_fitness_plan",
                func=generate_fitness_plan,
                description="""Generate a personalized fitness plan using core logic (deterministic algorithms, NOT LLM).
                
                ONLY call this tool when ALL required user data has been collected.
                This tool will:
                1. Validate all required fields are present
                2. Generate diet plan using BMR/TDEE calculations
                3. Generate workout plan based on experience and goals
                4. Save user and plan to database
                5. Generate LLM explanation of the plan
                
                Returns:
                    Success message with user_id and plan_id, or error message
                """
            ),
            Tool(
                name="get_collected_data",
                func=get_collected_data,
                description="""Get a summary of all data collected so far.
                
                Use this tool to see what information has already been collected from the user.
                
                Returns:
                    Summary of collected data
                """
            )
        ]
        
        return tools
    
    def _generate_plan_explanation(
        self,
        user_data: Dict[str, Any],
        diet_plan: Dict[str, Any],
        workout_plan: Dict[str, Any]
    ) -> str:
        """Generate plan explanation using LLM."""
        try:
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
DO NOT use markdown formatting - use plain text only."""
            
            response = self.llm.invoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            print(f"Error generating plan explanation: {e}")
            return f"Your personalized plan has been created based on your goal of {user_data.get('goal')}, {user_data.get('diet_type')} diet preferences, and {user_data.get('workout_experience')} workout experience level."
    
    def _create_agent(self):
        """Create the LangChain agent."""
        tools = self._create_tools()
        
        # Create ReAct prompt template with all required variables
        # This is the standard ReAct prompt format that includes tools and tool_names
        react_prompt = PromptTemplate.from_template("""You are a friendly and conversational fitness coach assistant. Your job is to collect user information step by step to create a personalized fitness plan.

CRITICAL INSTRUCTIONS:
1. Ask for ONE field at a time. Never ask for multiple fields in a single question.
2. Be natural and conversational. For example, ask "What's your name?" instead of "Please provide your name, age, gender, height, and weight."
3. After the user provides a value, use validate_and_save_field to save it, then check what to ask next.
4. Only use check_missing_fields to find the NEXT field to ask - it returns only ONE field.
5. After collecting all data, use generate_fitness_plan to create the plan.
6. Be friendly, encouraging, and patient. Make the conversation feel natural, not like a form.

Available tools:
{tools}

Tool names: {tool_names}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question (ask for ONE field only, be conversational)

Begin!

Question: {input}
Thought: {agent_scratchpad}""")
        
        # Create agent with the ReAct prompt
        agent = create_react_agent(self.llm, tools, react_prompt)
        
        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=10
        )
    
    def process_message(self, message: str, conversation_history: Optional[List[Dict]] = None) -> str:
        """
        Process a user message and return the agent's response.
        
        Args:
            message: User's message
            conversation_history: Optional list of previous messages for context
        
        Returns:
            Agent's response
        """
        if not self.agent_executor:
            raise ValueError("Agent not initialized")
        
        # Prepare chat history
        chat_history = []
        if conversation_history:
            for msg in conversation_history[-5:]:  # Last 5 messages for context
                chat_history.append(("human", msg.get("message", "")))
                chat_history.append(("ai", msg.get("response", "")))
        
        # For empty message (initial greeting), guide the agent to check missing fields first
        if not message or not message.strip():
            message = "Start the conversation by checking what information you need to collect first."
        
        try:
            result = self.agent_executor.invoke({
                "input": message,
                "chat_history": chat_history
            })
            
            response = result.get("output", "I apologize, I couldn't process that.")
            
            # Strip any markdown formatting
            import re
            response = re.sub(r'\*\*([^*]+)\*\*', r'\1', response)  # Remove **bold**
            response = re.sub(r'\*([^*]+)\*', r'\1', response)  # Remove *italic*
            response = re.sub(r'`([^`]+)`', r'\1', response)  # Remove `code`
            response = re.sub(r'#+\s*', '', response)  # Remove headers
            response = response.strip()
            
            return response
            
        except Exception as e:
            print(f"Error in LangChain agent: {e}")
            return f"I apologize, I encountered an error: {str(e)}. Please try again."
    
    def answer_followup_question(
        self,
        message: str,
        user_data: Dict[str, Any],
        diet_plan: Dict[str, Any],
        workout_plan: Dict[str, Any],
        conversation_history: Optional[List[Dict]] = None
    ) -> str:
        """Answer follow-up questions about the generated plan."""
        # Format plan context
        diet_context = f"""
Daily Nutritional Targets:
- Calories: {diet_plan.get('daily_targets', {}).get('calories', 'N/A')} kcal
- Protein: {diet_plan.get('daily_targets', {}).get('macros', {}).get('protein', 'N/A')}g
- Carbs: {diet_plan.get('daily_targets', {}).get('macros', {}).get('carbs', 'N/A')}g
- Fats: {diet_plan.get('daily_targets', {}).get('macros', {}).get('fats', 'N/A')}g
"""
        
        workout_context = f"""
Workout Plan:
- Total Workout Days: {workout_plan.get('total_workout_days', 'N/A')} days per week
- Session Duration: {workout_plan.get('session_duration', 'N/A')} minutes
"""
        
        prompt = f"""You are an enthusiastic, friendly, and knowledgeable fitness and nutrition coach. Answer the user's question about their personalized plan.

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

User's Question: {message}

IMPORTANT INSTRUCTIONS:
1. You can see their complete diet and workout plan above. Use this information to answer questions accurately.
2. If they ask to modify the plan (e.g., "Can I replace X with Y?", "I don't like this exercise", "Can I change Monday's meal?"), provide specific suggestions based on their plan.
3. For food swaps: Suggest alternatives that match their diet type ({user_data.get('diet_type')}) and avoid their allergies ({user_data.get('food_allergies', 'None')}) and disliked foods ({user_data.get('disliked_foods', 'None')}).
4. For workout modifications: Consider their experience level ({user_data.get('workout_experience')}) and provide safe alternatives.
5. Be conversational, friendly, and encouraging (2-3 sentences).
6. Always end with an open-ended question to keep the conversation going.
7. DO NOT use markdown formatting (no **bold**, *italic*, `code`, or # headers) - use plain text only.
8. Do not make medical claims. If asked about medical conditions, recommend consulting a healthcare professional.
"""
        
        try:
            response = self.llm.invoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # Strip markdown formatting
            import re
            response_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', response_text)
            response_text = re.sub(r'\*([^*]+)\*', r'\1', response_text)
            response_text = re.sub(r'`([^`]+)`', r'\1', response_text)
            response_text = re.sub(r'#+\s*', '', response_text)
            
            return response_text.strip()
        except Exception as e:
            print(f"Error generating follow-up response: {e}")
            return "I apologize, but I'm having trouble processing your question right now. Please try again."

