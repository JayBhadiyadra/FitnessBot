"""
Conversational flow management for collecting user data step by step.
"""
from typing import Dict, Any, Optional, Tuple
import uuid

class ConversationFlow:
    """Manages the conversational flow for data collection."""
    
    STEPS = [
        'personal_details',  # name, age, gender, height, weight
        'goal_planning',     # goal, target_weight
        'health_constraints', # medical_conditions, food_allergies, diet_type, disliked_foods
        'eating_lifestyle',  # meals_per_day, cooking_habits, wake_time, sleep_time, work_hours, activity_level
        'workout_info'       # workout_experience, workout_days_per_week, workout_duration
    ]
    
    STEP_FIELDS = {
        'personal_details': ['name', 'age', 'gender', 'height', 'weight'],
        'goal_planning': ['goal', 'target_weight'],
        'health_constraints': ['medical_conditions', 'food_allergies', 'diet_type', 'disliked_foods'],
        'eating_lifestyle': ['meals_per_day', 'cooking_habits', 'wake_time', 'sleep_time', 'work_hours', 'activity_level'],
        'workout_info': ['workout_experience', 'workout_days_per_week', 'workout_duration']
    }
    
    @staticmethod
    def validate_positive_number(value: Any, field_name: str) -> Tuple[bool, Optional[str]]:
        """Validate that a number is positive (greater than 0)."""
        try:
            # Convert to string first to preserve negative sign
            if isinstance(value, str):
                value_str = value.strip()
                # Check for negative sign explicitly
                if value_str.startswith('-'):
                    return False, f"Please enter a positive number for {field_name.replace('_', ' ')}. Negative values are not allowed. The value must be greater than 0."
                num_value = float(value_str)
            else:
                num_value = float(value)
            
            if num_value <= 0:
                return False, f"Please enter a positive number for {field_name.replace('_', ' ')}. Zero and negative values are not allowed. The value must be greater than 0."
            return True, None
        except (ValueError, TypeError):
            return False, f"Please enter a valid number for {field_name.replace('_', ' ')}."
    
    @staticmethod
    def validate_field(field_name: str, value: Any, step: str) -> Tuple[bool, Optional[str]]:
        """Validate a field based on its name and step."""
        # Positive number validation for numeric fields
        numeric_fields = ['age', 'height', 'weight', 'target_weight', 'meals_per_day', 
                          'workout_days_per_week', 'workout_duration']
        
        if field_name in numeric_fields:
            return ConversationFlow.validate_positive_number(value, field_name)
        
        # Name validation - reject common non-name responses
        if field_name == 'name':
            if not value or (isinstance(value, str) and not value.strip()):
                return False, "Please provide your name. If you prefer not to share, you can use a nickname or initials."
            value_lower = str(value).lower().strip()
            reject_patterns = ['no', 'nothing', 'none', "don't", "dont", 'skip', 'pass', 'not', 'n/a', 'na', 'nope', 'nah']
            if value_lower in reject_patterns or len(value.strip()) < 2:
                return False, "That doesn't look like a name. Please provide your name or a nickname."
            # Reject if it's just numbers
            if value.strip().isdigit():
                return False, "Please provide a name, not just numbers."
        
        # Diet type validation
        if field_name == 'diet_type':
            if not value or (isinstance(value, str) and not value.strip()):
                return False, "Please specify your diet type. Options: vegetarian, non-vegetarian, vegan, or pescatarian."
            value_lower = str(value).lower().strip()
            valid_diet_types = ['veg', 'vegetarian', 'non_veg', 'non-veg', 'vegan', 'pescatarian']
            if value_lower not in valid_diet_types:
                # Try to normalize
                if 'vegan' in value_lower:
                    return True, None  # Will be normalized to 'vegan'
                elif 'pescatarian' in value_lower or 'pesca' in value_lower:
                    return True, None  # Will be normalized to 'pescatarian'
                elif any(word in value_lower for word in ['veg', 'vegetarian']) and 'non' not in value_lower:
                    return True, None  # Will be normalized to 'veg'
                elif any(word in value_lower for word in ['non', 'meat', 'chicken']):
                    return True, None  # Will be normalized to 'non_veg'
                else:
                    return False, "Please specify a valid diet type: vegetarian, non-vegetarian, vegan, or pescatarian."
        
        # Required field check
        if not value or (isinstance(value, str) and not value.strip()):
            if field_name in ['medical_conditions', 'food_allergies', 'disliked_foods', 'target_weight']:
                return True, None  # These are optional
            return False, f"{field_name.replace('_', ' ').title()} is required."
        
        # Specific validations
        if field_name == 'age':
            try:
                age = int(value)
                if age < 13 or age > 100:
                    return False, "Age must be between 13 and 100."
            except:
                return False, "Please enter a valid age."
        
        if field_name == 'height':
            try:
                height = float(value)
                if height < 100 or height > 250:
                    return False, "Height must be between 100 and 250 cm."
            except:
                return False, "Please enter a valid height."
        
        if field_name == 'weight':
            try:
                weight = float(value)
                if weight < 30 or weight > 300:
                    return False, "Weight must be between 30 and 300 kg."
            except:
                return False, "Please enter a valid weight."
        
        if field_name == 'target_weight':
            try:
                target = float(value)
                if target < 30 or target > 300:
                    return False, "Target weight must be between 30 and 300 kg."
            except:
                return False, "Please enter a valid target weight."
        
        return True, None
    
    @staticmethod
    def get_next_step(current_step: str) -> Optional[str]:
        """Get the next step in the flow."""
        try:
            current_index = ConversationFlow.STEPS.index(current_step)
            if current_index < len(ConversationFlow.STEPS) - 1:
                return ConversationFlow.STEPS[current_index + 1]
            return None  # All steps completed
        except ValueError:
            return ConversationFlow.STEPS[0]
    
    @staticmethod
    def is_step_complete(collected_data: Dict[str, Any], step: str) -> bool:
        """Check if a step is complete."""
        required_fields = ConversationFlow.STEP_FIELDS.get(step, [])
        for field in required_fields:
            # Optional fields
            if field in ['medical_conditions', 'food_allergies', 'disliked_foods', 'target_weight']:
                continue
            # Check if field exists and has a non-empty value
            if field not in collected_data:
                return False
            value = collected_data[field]
            if value is None or (isinstance(value, str) and not value.strip()):
                return False
        return True
    
    @staticmethod
    def generate_session_id() -> str:
        """Generate a unique session ID."""
        return str(uuid.uuid4())

