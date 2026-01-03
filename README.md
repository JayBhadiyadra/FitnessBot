# Fitness Plan Chatbot

A personalized diet and workout plan chatbot built with Python, FastAPI, and PostgreSQL. The chatbot collects user information through natural conversation and generates personalized fitness plans with beautiful table displays.

## Features

- **Conversational Data Collection**: Collects all required user information through natural chat interface
- **Core Plan Generation**: Generates diet and workout plans using deterministic algorithms (no LLM)
- **LLM Explanations**: Uses Gemini AI only for plan explanations and follow-up questions
- **Table Format Display**: Plans are displayed in readable table format within the chat interface
- **PostgreSQL Database**: Stores all user data, plans, and conversation history
- **Follow-up Support**: Answers questions about food swaps, workout modifications, and plan adjustments
- **Plan Modifications**: Users can ask the LLM to modify their plans through natural conversation

## Architecture

```
User → Chat Interface → Conversation Flow → Data Extraction → Validation
                                                              ↓
                                              Plan Generation (Core Logic - No LLM)
                                                              ↓
                                              Explanation Generation (LLM)
                                                              ↓
                                              Display Plan in Tables + LLM Explanation
                                                              ↓
                                              Follow-up Questions (LLM with Plan Context)
```

## Requirements

- Python 3.10+
- PostgreSQL 12+
- Google Gemini API Key

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv fitness_venv
   fitness_venv\Scripts\activate  # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your `.env` file:
   ```env
   DATABASE_URL=your_db_uri
   GEMINI_API_KEY=your_api_key_here
   HOST=0.0.0.0
   PORT=8000
   ```

5. Create the PostgreSQL database:
   ```sql
   CREATE DATABASE fitness_chatbot;
   ```

6. Run the application:
   ```bash
   python run.py
   ```

7. Open your browser:
   ```
   http://localhost:8000
   ```

8. Click the chatbot icon (bottom right) to start chatting!

## How It Works

### 1. **Start Conversation**
   - Open the website at `http://localhost:8000`
   - Chat window opens automatically (or click the chatbot icon in bottom right)
   - Bot greets you with a personalized message and asks for your name

### 2. **Data Collection** (Conversational Flow)
   The bot collects information through natural conversation in these steps:
   
   **Step 1: Personal Details**
   - Name, age, gender, height (cm), weight (kg)
   
   **Step 2: Goal Planning**
   - Fitness goal (fat_loss, muscle_gain, or maintenance)
   - Target weight (if applicable)
   
   **Step 3: Health Constraints**
   - Medical conditions (optional)
   - Food allergies (optional)
   - Diet type (vegetarian, non-vegetarian, vegan, pescatarian)
   - Disliked foods (optional)
   
   **Step 4: Eating Habits & Lifestyle**
   - Meals per day (2-6)
   - Cooking habits (home_cooked, mixed, outside_food)
   - Wake time (HH:MM format)
   - Sleep time (HH:MM format)
   - Work hours
   - Activity level (sedentary, moderate, active)
   
   **Step 5: Workout Information**
   - Workout experience (beginner, intermediate, advanced)
   - Workout days per week (1-7)
   - Workout duration per session (15-180 minutes)
   
   All inputs are validated in real-time with helpful error messages.

### 3. **Plan Generation** (Automatic)
   When all required data is collected:
   
   **Core Logic (Deterministic - NO LLM):**
   - Calculates BMR (Basal Metabolic Rate) using Mifflin-St Jeor equation
   - Calculates TDEE (Total Daily Energy Expenditure) based on activity level
   - Determines target calories based on goal (surplus for muscle gain, deficit for fat loss)
   - Calculates macronutrient distribution (protein, carbs, fats)
   - Generates weekly meal plan with:
     - Daily meals (breakfast, lunch, dinner, snacks)
     - Food items matching diet type, allergies, and preferences
     - Calorie distribution across meals
   - Generates weekly workout plan with:
     - Workout split based on experience and days available
     - Exercises for each day
     - Duration and intensity
     - Recovery guidance
   
   **LLM Explanation:**
   - Gemini AI generates a personalized explanation of why the plan is best for the user
   - Explains the nutritional targets and workout approach
   - Provides motivation and guidance

### 4. **Plan Display**
   The generated plan is displayed in the chat interface with:
   - **Daily Nutritional Targets Table**: Calories, Protein, Carbs, Fats
   - **Weekly Diet Plan Table**: Day, Meal Type, Food, Calories
   - **Weekly Workout Plan Table**: Day, Type, Exercises, Duration, Intensity
   - **LLM Explanation**: Personalized text explaining the plan
   - **Recovery Guidance**: Tips based on experience level

### 5. **Follow-up Questions**
   After plan generation, users can ask questions in the chat:
   - **Food Swaps**: "Can I replace Monday's lunch with something else?"
   - **Workout Modifications**: "I don't like squats, what can I do instead?"
   - **Meal Alternatives**: "Suggest a vegetarian alternative for Tuesday's dinner"
   - **General Questions**: "Why is this plan good for me?"
   - **Plan Adjustments**: "Can I modify the workout schedule?"
   
   The LLM has full context of:
   - The complete diet and workout plan
   - User's profile (diet type, allergies, experience level)
   - Conversation history
   
   It provides specific, personalized suggestions based on the actual plan data.

## Key Files

### Backend
- `app/main.py` - FastAPI application with all endpoints and conversation handling
- `app/core_logic.py` - Plan generation logic (NO LLM) - BMR, TDEE, meal/workout plans
- `app/gemini_service.py` - LLM service for explanations and follow-up questions
- `app/conversation_flow.py` - Manages conversation steps, validation, and field extraction
- `app/conversation_summary.py` - Generates conversation summaries for LLM context
- `app/models.py` - SQLAlchemy database models (User, UserPlan, Conversation, ConversationState)
- `app/schemas.py` - Pydantic models for API request/response validation
- `app/database.py` - PostgreSQL database connection and session management

### Frontend
- `static/index.html` - Chat interface HTML (floating chatbot icon and chat window)
- `static/style.css` - Styling for chat interface and plan tables
- `static/script.js` - JavaScript for chat interactions, API calls, and plan display

### Configuration
- `run.py` - Application entry point
- `requirements.txt` - Python dependencies
- `.env` - Environment variables (DATABASE_URL, GEMINI_API_KEY, HOST, PORT)

## Important Notes

- **Conversational Interface**: Data collection happens through natural conversation in a chat window, not forms
- **Plan Display**: Plans are automatically displayed in table format within the chat interface when generated
- **Core Logic**: Plan generation uses deterministic algorithms (BMR, TDEE calculations), NOT LLM
- **LLM Usage**: Gemini AI is ONLY used for:
  - Plan explanations (why the plan is good for the user)
  - Follow-up question answers (with full plan context)
  - Conversational responses during data collection
- **PostgreSQL**: All data is stored in PostgreSQL database (users, plans, conversations)
- **Validation**: All inputs are validated in real-time (positive numbers, valid ranges, required fields)
- **Plan Modifications**: Users can modify plans through natural conversation - LLM suggests alternatives based on the actual plan data

## Note
- I have integrated the LnagChain agent in saperate branch but that is not working proper in free api so I have just added the code for reference.

## License

This project is for interview/assignment purposes.
