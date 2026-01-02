"""
Generate conversation summaries for better context awareness.
"""
from typing import Dict, Any, List

def generate_conversation_summary(collected_data: Dict[str, Any], current_step: str) -> str:
    """Generate a summary of what has been collected so far."""
    summary_parts = []
    
    if collected_data.get('name'):
        summary_parts.append(f"Name: {collected_data['name']}")
    
    if collected_data.get('age'):
        summary_parts.append(f"Age: {collected_data['age']} years")
    
    if collected_data.get('gender'):
        summary_parts.append(f"Gender: {collected_data['gender']}")
    
    if collected_data.get('height'):
        summary_parts.append(f"Height: {collected_data['height']} cm")
    
    if collected_data.get('weight'):
        summary_parts.append(f"Weight: {collected_data['weight']} kg")
    
    if collected_data.get('goal'):
        summary_parts.append(f"Goal: {collected_data['goal']}")
    
    if collected_data.get('target_weight'):
        summary_parts.append(f"Target Weight: {collected_data['target_weight']} kg")
    
    if collected_data.get('diet_type'):
        summary_parts.append(f"Diet Type: {collected_data['diet_type']}")
    
    if collected_data.get('food_allergies'):
        summary_parts.append(f"Food Allergies: {collected_data['food_allergies']}")
    
    if collected_data.get('disliked_foods'):
        summary_parts.append(f"Disliked Foods: {collected_data['disliked_foods']}")
    
    if collected_data.get('meals_per_day'):
        summary_parts.append(f"Meals per day: {collected_data['meals_per_day']}")
    
    if collected_data.get('cooking_habits'):
        summary_parts.append(f"Cooking Habits: {collected_data['cooking_habits']}")
    
    if collected_data.get('wake_time'):
        summary_parts.append(f"Wake Time: {collected_data['wake_time']}")
    
    if collected_data.get('sleep_time'):
        summary_parts.append(f"Sleep Time: {collected_data['sleep_time']}")
    
    if collected_data.get('work_hours'):
        summary_parts.append(f"Work Hours: {collected_data['work_hours']}")
    
    if collected_data.get('activity_level'):
        summary_parts.append(f"Activity Level: {collected_data['activity_level']}")
    
    if collected_data.get('workout_experience'):
        summary_parts.append(f"Workout Experience: {collected_data['workout_experience']}")
    
    if collected_data.get('workout_days_per_week'):
        summary_parts.append(f"Workout Days per Week: {collected_data['workout_days_per_week']}")
    
    if collected_data.get('workout_duration'):
        summary_parts.append(f"Workout Duration: {collected_data['workout_duration']} minutes")
    
    if summary_parts:
        return "Information collected so far:\n" + "\n".join(f"- {part}" for part in summary_parts)
    else:
        return "No information collected yet."

def get_missing_fields(collected_data: Dict[str, Any], current_step: str) -> List[str]:
    """Get list of fields that still need to be collected for current step."""
    from app.conversation_flow import ConversationFlow
    
    step_fields = ConversationFlow.STEP_FIELDS.get(current_step, [])
    missing = []
    
    for field in step_fields:
        if field not in collected_data or not collected_data[field]:
            # Skip optional fields
            if field not in ['medical_conditions', 'food_allergies', 'disliked_foods', 'target_weight']:
                missing.append(field)
    
    return missing

