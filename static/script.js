// API Configuration
const API_BASE_URL = window.location.origin;
let sessionId = null;
let isInitialized = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await initializeChat();
    setupEventListeners();
});

// Initialize chat session
async function initializeChat() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/chat/start`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        if (data.session_id) {
            sessionId = data.session_id;
            isInitialized = true;
            
            // Add initial bot message
            if (data.response) {
                addMessage(data.response, 'bot');
            }
        } else {
            throw new Error('Failed to create session');
        }
    } catch (error) {
        console.error('Error initializing chat:', error);
        addMessage('Sorry, I encountered an error. Please refresh the page.', 'bot');
    }
}

// Setup event listeners
function setupEventListeners() {
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

// Toggle chat window
function toggleChat() {
    const chatWindow = document.getElementById('chat-window');
    if (chatWindow.classList.contains('hidden')) {
        chatWindow.classList.remove('hidden');
        document.getElementById('chat-input').focus();
    } else {
        chatWindow.classList.add('hidden');
    }
}

// Handle key press
function handleKeyPress(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

// Send message
async function sendMessage() {
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const message = chatInput.value.trim();
    
    if (!message || !sessionId || !isInitialized) return;
    
    // Add user message to chat
    addMessage(message, 'user');
    chatInput.value = '';
    sendBtn.disabled = true;
    
    // Show loading indicator
    const loadingMessage = addMessage('...', 'bot', true);
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/chat/message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });
        
        const data = await response.json();
        
        // Remove loading message
        loadingMessage.remove();
        
        if (data.response) {
            addMessage(data.response, 'bot');
            
            // Check if plan data is available and display it in table format
            // This handles both initial plan generation and follow-up responses that include plan data
            if (data.diet_plan && data.workout_plan) {
                // Check if plan is already displayed to avoid duplicates
                const existingPlan = document.querySelector('.plan-display');
                if (!existingPlan || data.plan_generated) {
                    displayPlan(data.diet_plan, data.workout_plan);
                }
            }
        } else if (data.error) {
            addMessage('Sorry, I encountered an error. Please try again.', 'bot');
        }
    } catch (error) {
        console.error('Error sending message:', error);
        loadingMessage.remove();
        addMessage('Sorry, I encountered an error. Please try again.', 'bot');
    } finally {
        sendBtn.disabled = false;
        chatInput.focus();
    }
}

// Add message to chat
function addMessage(text, type, isLoading = false) {
    const messagesContainer = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    if (isLoading) {
        const loadingSpan = document.createElement('span');
        loadingSpan.className = 'loading';
        loadingSpan.textContent = '...';
        contentDiv.appendChild(loadingSpan);
    } else {
        // Split text by newlines and create paragraphs
        const paragraphs = text.split('\n').filter(p => p.trim());
        if (paragraphs.length === 0) {
            paragraphs.push(text);
        }
        paragraphs.forEach(p => {
            const pTag = document.createElement('p');
            pTag.textContent = p.trim();
            contentDiv.appendChild(pTag);
        });
    }
    
    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    return messageDiv;
}

// Display plan in table format
function displayPlan(dietPlan, workoutPlan) {
    const messagesContainer = document.getElementById('chat-messages');
    const planDiv = document.createElement('div');
    planDiv.className = 'plan-display';
    
    let planHTML = '<div class="plan-container">';
    
    // Daily Targets Section
    if (dietPlan.daily_targets) {
        planHTML += `
            <div class="plan-section">
                <h3>📊 Daily Nutritional Targets</h3>
                <div class="targets-grid">
                    <div class="target-card">
                        <h4>Calories</h4>
                        <p class="target-value">${dietPlan.daily_targets.calories || 'N/A'}</p>
                        <span class="target-unit">kcal</span>
                    </div>
                    <div class="target-card">
                        <h4>Protein</h4>
                        <p class="target-value">${dietPlan.daily_targets.macros?.protein || 'N/A'}</p>
                        <span class="target-unit">g</span>
                    </div>
                    <div class="target-card">
                        <h4>Carbs</h4>
                        <p class="target-value">${dietPlan.daily_targets.macros?.carbs || 'N/A'}</p>
                        <span class="target-unit">g</span>
                    </div>
                    <div class="target-card">
                        <h4>Fats</h4>
                        <p class="target-value">${dietPlan.daily_targets.macros?.fats || 'N/A'}</p>
                        <span class="target-unit">g</span>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Weekly Diet Plan Table
    if (dietPlan.weekly_plan) {
        planHTML += `
            <div class="plan-section">
                <h3>🍽️ Weekly Diet Plan</h3>
                <div class="table-container">
                    <table class="plan-table">
                        <thead>
                            <tr>
                                <th>Day</th>
                                <th>Meal Type</th>
                                <th>Food</th>
                                <th>Calories</th>
                            </tr>
                        </thead>
                        <tbody>
        `;
        
        const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
        days.forEach(day => {
            const dayPlan = dietPlan.weekly_plan[day];
            if (dayPlan && dayPlan.meals) {
                dayPlan.meals.forEach((meal, index) => {
                    planHTML += `
                        <tr>
                            ${index === 0 ? `<td rowspan="${dayPlan.meals.length}" class="day-cell">${day}</td>` : ''}
                            <td>${meal.meal_type}</td>
                            <td>${meal.food}</td>
                            <td>${meal.calories} kcal</td>
                        </tr>
                    `;
                });
            }
        });
        
        planHTML += `
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
    
    // Weekly Workout Plan Table
    if (workoutPlan.weekly_plan) {
        planHTML += `
            <div class="plan-section">
                <h3>💪 Weekly Workout Plan</h3>
                <div class="table-container">
                    <table class="plan-table">
                        <thead>
                            <tr>
                                <th>Day</th>
                                <th>Type</th>
                                <th>Exercises</th>
                                <th>Duration</th>
                                <th>Intensity</th>
                            </tr>
                        </thead>
                        <tbody>
        `;
        
        const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
        days.forEach(day => {
            const dayPlan = workoutPlan.weekly_plan[day];
            if (dayPlan) {
                const exercises = Array.isArray(dayPlan.exercises) 
                    ? dayPlan.exercises.join(', ') 
                    : (dayPlan.exercises || 'Rest');
                planHTML += `
                    <tr>
                        <td>${day}</td>
                        <td>${dayPlan.type || 'Rest'}</td>
                        <td>${exercises}</td>
                        <td>${dayPlan.duration_minutes || 0} min</td>
                        <td>${dayPlan.intensity || 'rest'}</td>
                    </tr>
                `;
            }
        });
        
        planHTML += `
                        </tbody>
                    </table>
                </div>
            `;
        
        if (workoutPlan.recovery_guidance) {
            planHTML += `
                <div class="recovery-note">
                    <strong>💡 Recovery Guidance:</strong> ${workoutPlan.recovery_guidance}
                </div>
            `;
        }
        
        planHTML += `
            </div>
        `;
    }
    
    planHTML += '</div>';
    planDiv.innerHTML = planHTML;
    messagesContainer.appendChild(planDiv);
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}
