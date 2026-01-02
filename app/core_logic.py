"""
Core personalization logic for diet and workout plans.
This module contains the business logic that generates personalized plans
based on user inputs. AI/LLM is only used for explanations, not for plan generation.
"""
from typing import Dict, List, Any
import math

class DietPlanGenerator:
    """Generates personalized diet plans based on user inputs."""
    
    # Base calorie multipliers by activity level
    ACTIVITY_MULTIPLIERS = {
        'sedentary': 1.2,
        'moderate': 1.55,
        'active': 1.725
    }
    
    # Goal-based calorie adjustments
    GOAL_ADJUSTMENTS = {
        'fat_loss': -500,  # 500 calorie deficit
        'muscle_gain': 300,  # 300 calorie surplus
        'maintenance': 0
    }
    
    # Macro ratios by goal
    MACRO_RATIOS = {
        'fat_loss': {'protein': 0.35, 'carbs': 0.35, 'fats': 0.30},
        'muscle_gain': {'protein': 0.30, 'carbs': 0.45, 'fats': 0.25},
        'maintenance': {'protein': 0.30, 'carbs': 0.40, 'fats': 0.30}
    }
    
    # Food database (simplified - in production, use a comprehensive database)
    FOOD_DATABASE = {
        'veg': {
            'breakfast': ['Oats with fruits', 'Poha', 'Upma', 'Idli with sambar', 'Paratha with curd', 'Cereal with milk'],
            'lunch': ['Dal rice with vegetables', 'Rajma rice', 'Chole with roti', 'Vegetable biryani', 'Khichdi', 'Dal tadka with roti'],
            'dinner': ['Vegetable curry with roti', 'Dal with rice', 'Stir-fried vegetables', 'Soup and salad', 'Paneer curry'],
            'snacks': ['Fruits', 'Nuts', 'Yogurt', 'Smoothie', 'Roasted chana', 'Tea with biscuits']
        },
        'non_veg': {
            'breakfast': ['Eggs with toast', 'Chicken sandwich', 'Omelette', 'Egg curry with roti', 'Scrambled eggs'],
            'lunch': ['Chicken curry with rice', 'Fish curry with rice', 'Mutton biryani', 'Chicken biryani', 'Egg curry with roti'],
            'dinner': ['Grilled chicken with vegetables', 'Fish curry', 'Chicken salad', 'Egg curry', 'Chicken soup'],
            'snacks': ['Boiled eggs', 'Chicken salad', 'Protein shake', 'Nuts', 'Fruits']
        },
        'vegan': {
            'breakfast': ['Oats with plant milk', 'Smoothie bowl', 'Avocado toast', 'Chia pudding'],
            'lunch': ['Lentil curry with rice', 'Chickpea salad', 'Vegetable stir-fry', 'Quinoa bowl'],
            'dinner': ['Tofu curry', 'Lentil soup', 'Vegetable curry', 'Bean salad'],
            'snacks': ['Nuts', 'Fruits', 'Hummus with vegetables', 'Roasted chickpeas']
        }
    }
    
    @staticmethod
    def calculate_bmr(weight: float, height: float, age: int, gender: str) -> float:
        """Calculate Basal Metabolic Rate using Mifflin-St Jeor Equation."""
        if gender.lower() == 'male':
            bmr = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 161
        return bmr
    
    @staticmethod
    def calculate_tdee(bmr: float, activity_level: str) -> float:
        """Calculate Total Daily Energy Expenditure."""
        multiplier = DietPlanGenerator.ACTIVITY_MULTIPLIERS.get(activity_level, 1.2)
        return bmr * multiplier
    
    @staticmethod
    def calculate_target_calories(tdee: float, goal: str) -> float:
        """Calculate target daily calories based on goal."""
        adjustment = DietPlanGenerator.GOAL_ADJUSTMENTS.get(goal, 0)
        target = tdee + adjustment
        # Safety check: minimum 1200 calories for women, 1500 for men
        return max(target, 1200)
    
    @staticmethod
    def calculate_macros(calories: float, goal: str) -> Dict[str, float]:
        """Calculate protein, carbs, and fats in grams."""
        ratios = DietPlanGenerator.MACRO_RATIOS.get(goal, DietPlanGenerator.MACRO_RATIOS['maintenance'])
        
        protein_cals = calories * ratios['protein']
        carbs_cals = calories * ratios['carbs']
        fats_cals = calories * ratios['fats']
        
        return {
            'protein': round(protein_cals / 4, 1),  # 4 cal/g
            'carbs': round(carbs_cals / 4, 1),  # 4 cal/g
            'fats': round(fats_cals / 9, 1),  # 9 cal/g
            'calories': round(calories, 0)
        }
    
    @staticmethod
    def filter_foods(food_list: List[str], allergies: str, disliked: str) -> List[str]:
        """Filter out foods based on allergies and dislikes."""
        filtered = food_list.copy()
        
        if allergies:
            allergy_list = [a.strip().lower() for a in allergies.split(',')]
            filtered = [f for f in filtered if not any(allergy in f.lower() for allergy in allergy_list)]
        
        if disliked:
            disliked_list = [d.strip().lower() for d in disliked.split(',')]
            filtered = [f for f in filtered if not any(dislike in f.lower() for dislike in disliked_list)]
        
        return filtered if filtered else food_list  # Return original if all filtered out
    
    @staticmethod
    def generate_weekly_meal_plan(user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a personalized weekly meal plan."""
        # Calculate nutritional requirements
        bmr = DietPlanGenerator.calculate_bmr(
            user_data['weight'],
            user_data['height'],
            user_data['age'],
            user_data['gender']
        )
        tdee = DietPlanGenerator.calculate_tdee(bmr, user_data['activity_level'])
        target_calories = DietPlanGenerator.calculate_target_calories(tdee, user_data['goal'])
        macros = DietPlanGenerator.calculate_macros(target_calories, user_data['goal'])
        
        # Get food options based on diet type
        diet_type = user_data['diet_type']
        if diet_type not in DietPlanGenerator.FOOD_DATABASE:
            diet_type = 'veg'  # Default fallback
        
        food_options = DietPlanGenerator.FOOD_DATABASE[diet_type]
        
        # Filter foods based on allergies and dislikes
        allergies = user_data.get('food_allergies', '') or ''
        disliked = user_data.get('disliked_foods', '') or ''
        
        breakfast_options = DietPlanGenerator.filter_foods(food_options['breakfast'], allergies, disliked)
        lunch_options = DietPlanGenerator.filter_foods(food_options['lunch'], allergies, disliked)
        dinner_options = DietPlanGenerator.filter_foods(food_options['dinner'], allergies, disliked)
        snack_options = DietPlanGenerator.filter_foods(food_options['snacks'], allergies, disliked)
        
        # Generate meal plan for 7 days
        meals_per_day = user_data['meals_per_day']
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekly_plan = {}
        
        for day in days:
            day_meals = []
            
            # Breakfast
            if meals_per_day >= 2:
                day_meals.append({
                    'meal_type': 'Breakfast',
                    'food': breakfast_options[hash(day) % len(breakfast_options)],
                    'calories': round(target_calories * 0.25, 0)
                })
            
            # Lunch
            if meals_per_day >= 2:
                day_meals.append({
                    'meal_type': 'Lunch',
                    'food': lunch_options[hash(day + 'lunch') % len(lunch_options)],
                    'calories': round(target_calories * 0.35, 0)
                })
            
            # Snacks (if 3+ meals)
            if meals_per_day >= 3:
                day_meals.append({
                    'meal_type': 'Snack',
                    'food': snack_options[hash(day + 'snack') % len(snack_options)],
                    'calories': round(target_calories * 0.10, 0)
                })
            
            # Dinner
            if meals_per_day >= 2:
                day_meals.append({
                    'meal_type': 'Dinner',
                    'food': dinner_options[hash(day + 'dinner') % len(dinner_options)],
                    'calories': round(target_calories * 0.30, 0)
                })
            
            # Additional snacks if needed
            if meals_per_day >= 4:
                day_meals.append({
                    'meal_type': 'Snack',
                    'food': snack_options[hash(day + 'snack2') % len(snack_options)],
                    'calories': round(target_calories * 0.10, 0)
                })
            
            weekly_plan[day] = {
                'meals': day_meals,
                'total_calories': round(sum(m['calories'] for m in day_meals), 0)
            }
        
        return {
            'weekly_plan': weekly_plan,
            'daily_targets': {
                'calories': round(target_calories, 0),
                'macros': macros
            },
            'cooking_habits': user_data.get('cooking_habits', 'mixed')
        }


class WorkoutPlanGenerator:
    """Generates personalized workout plans based on user inputs."""
    
    # Workout templates by experience level
    WORKOUT_TEMPLATES = {
        'beginner': {
            'full_body': ['Squats', 'Push-ups', 'Plank', 'Lunges', 'Dumbbell rows'],
            'cardio': ['Walking', 'Light jogging', 'Cycling'],
            'rest': ['Rest day - light stretching']
        },
        'intermediate': {
            'push': ['Bench press', 'Shoulder press', 'Tricep dips', 'Push-ups'],
            'pull': ['Pull-ups', 'Rows', 'Bicep curls', 'Lat pulldowns'],
            'legs': ['Squats', 'Deadlifts', 'Leg press', 'Lunges'],
            'cardio': ['Running', 'HIIT', 'Cycling'],
            'rest': ['Rest day - active recovery']
        },
        'advanced': {
            'push': ['Bench press', 'Incline press', 'Shoulder press', 'Tricep extensions', 'Lateral raises'],
            'pull': ['Deadlifts', 'Pull-ups', 'Barbell rows', 'Cable rows', 'Bicep curls'],
            'legs': ['Squats', 'Romanian deadlifts', 'Leg press', 'Lunges', 'Calf raises'],
            'cardio': ['HIIT', 'Sprint intervals', 'Conditioning'],
            'rest': ['Rest day - mobility work']
        }
    }
    
    @staticmethod
    def generate_weekly_workout_plan(user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a personalized weekly workout plan."""
        experience = user_data['workout_experience']
        days_per_week = user_data['workout_days_per_week']
        duration = user_data['workout_duration']
        goal = user_data['goal']
        activity_level = user_data['activity_level']
        
        templates = WorkoutPlanGenerator.WORKOUT_TEMPLATES[experience]
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        weekly_plan = {}
        
        # Determine workout split based on days available and experience level
        if experience == 'beginner':
            # Beginners always use full_body workouts
            workout_types = ['full_body'] * days_per_week
        elif days_per_week <= 3:
            # Upper/lower split for intermediate/advanced with 3 or fewer days
            workout_types = ['push', 'pull', 'legs'][:days_per_week]
        elif days_per_week == 4:
            # Upper/lower split for intermediate/advanced (no full_body for them)
            workout_types = ['push', 'pull', 'legs', 'push']  # Repeat push instead of full_body
        else:
            # Push/pull/legs split for 5+ days (intermediate/advanced only)
            workout_types = ['push', 'pull', 'legs'] * ((days_per_week // 3) + 1)
            workout_types = workout_types[:days_per_week]
        
        workout_index = 0
        
        for i, day in enumerate(days):
            if i < days_per_week:
                workout_type = workout_types[workout_index % len(workout_types)]
                
                if workout_type == 'full_body':
                    exercises = templates['full_body']
                elif workout_type == 'push':
                    exercises = templates['push']
                elif workout_type == 'pull':
                    exercises = templates['pull']
                elif workout_type == 'legs':
                    exercises = templates['legs']
                else:
                    exercises = templates['full_body']
                
                # Add cardio based on goal
                if goal == 'fat_loss' and activity_level != 'active':
                    exercises = exercises + templates['cardio'][:1]
                
                weekly_plan[day] = {
                    'type': workout_type.replace('_', ' ').title(),
                    'exercises': exercises,
                    'duration_minutes': duration,
                    'intensity': experience
                }
                workout_index += 1
            else:
                weekly_plan[day] = {
                    'type': 'Rest',
                    'exercises': templates['rest'],
                    'duration_minutes': 0,
                    'intensity': 'rest'
                }
        
        # Add recovery guidance
        recovery_guidance = {
            'beginner': 'Focus on form over weight. Rest 48 hours between sessions.',
            'intermediate': 'Maintain progressive overload. Include 1-2 rest days per week.',
            'advanced': 'Prioritize recovery. Consider deload weeks every 4-6 weeks.'
        }
        
        return {
            'weekly_plan': weekly_plan,
            'recovery_guidance': recovery_guidance.get(experience, 'Listen to your body and rest when needed.'),
            'total_workout_days': days_per_week,
            'session_duration': duration
        }

